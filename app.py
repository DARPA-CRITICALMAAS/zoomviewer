#!/usr/bin/env python
import flask
from PIL import Image
import math
import io
import glob
import os
import threading
import csv
import argparse
import pathlib

# default tile size, this is the size of the tiles used for the zoomable image viewer
tile_size = 256
# disable the image size limit, this is needed for large images
Image.MAX_IMAGE_PIXELS = None

# list of images and models, this in initialized at startup
image_list = {}
model_list = {}

# the flask app
app = flask.Flask("Result Viewer", static_url_path="", static_folder="static")

# this holds the current viewed image in memory to speed things up.
img = {
  "name": None,
  "model": None,
  "feature": None,
  "raw": None,
  "extracted": None,
  "maxlevel": 0
}

# lock to make sure only one process is creating the zoomed image
lock = threading.Semaphore()

# --------------------------------------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------------------------------------

def load_image_list(directory):
  """
  Return a list of all raw images. This is the base list of maps and all will be
  used to find the features associated with the maps
  @param directory: the directory to search for raw images
  """
  global image_list
  for f in glob.glob(f"{directory}/*.tif"):
    name = os.path.basename(f)[:-4]
    if name.endswith(".cog"):
      name = name[:-4]
    image_list[name] = f

def load_model_list(directory):
  """
  Load the model list from the specified directory.
  @param directory: the directory to search for models
  """
  global model_list
  for m in glob.glob(f"{directory}/*"):
    if os.path.isdir(m):
      model_list[os.path.basename(m)] = m

def check_path(name, model=None, feature=None):
  """
  Try to find the path to the image. This will use some common path checks.
  @param name: the name of the image to find
  @param model: the model to use to find the feature
  @param feature: the feature to find
  """
  # raw image
  if not model or not feature:
    fpath = f"data/raw/{name}.tif"
    if os.path.exists(fpath):
      return fpath
    fpath = f"data/raw/{name}.cog.tif"
    if os.path.exists(fpath):
      return fpath
    return None

  # validation results
  fpath = f"{model_list[model]}/{name}/val_{name}_{feature}.tif"
  if os.path.exists(fpath):
    return fpath

  # extracted image
  fpath = f"{model_list[model]}/{name}/{name}_{feature}.tif"
  if os.path.exists(fpath):
    return fpath
  fpath = f"{model_list[model]}/{name}_{feature}.tif"
  if os.path.exists(fpath):
    return fpath
  return None

def load_image(name, model=None, feature=None):
  """
  Load the image into memory. This will load the raw image and the extracted image
  into memory. The raw image is used for the base image and the extracted image is
  used as an overlay.
  @param name: the name of the image to load
  @param model: the extracted image is associated with this model
  @param feature: the feature to load
  """
  lock.acquire()
  if img["name"] != name:
    fpath = check_path(name)
    if not fpath:
      lock.release()
      return
    image = Image.open(fpath)
    img["maxlevel"] = int(math.ceil(math.log(max(image.width, image.height), 2))) + 1
    img["name"] = name
    img["model"] = model
    img["feature"] = feature
    img["raw"] = [None] * img["maxlevel"]
    img["raw"][-1] = image
    img["extracted"] = [None] * img["maxlevel"]
  if model and feature:
    if model != img["model"] or feature != img["feature"]:
      img["model"] = model
      img["feature"] = feature
      img["extracted"] = [None] * img["maxlevel"]
      fpath = check_path(name, model, feature)
      if fpath:
        image = Image.open(fpath)
        img["extracted"][-1] = image
  lock.release()

def send_image(img, transparent=False, quality=70):
  """
  Send the image as stream of bytes back to the client.
  @param img: the image to send
  @param transparent: if the image should be sent as a transparent image
  @param quality: the quality of the image
  """
  img_io = io.BytesIO()
  if transparent:
    if img.mode == "L":
      img.save(img_io, 'PNG', transparency=0)
    else:
      img.save(img_io, 'PNG', transparency=(0,0,0))
  else:
    img.save(img_io, 'PNG')
  img_io.seek(0)
  return flask.send_file(img_io, mimetype='image/jpeg')

# --------------------------------------------------------------------------------
# REST ENDPOINTS
# --------------------------------------------------------------------------------

@app.route('/')
def home():
  """
  Return the home page for the service. This is the page with the zoomable image viewer.
  """
  return flask.render_template("index.html",
                               model_list=sorted(model_list.keys(), key=str.casefold),
                               image_list=sorted(image_list.keys(), key=str.casefold))


@app.route('/dzi')
def images():
  """
  Return list of maps, this is used for debugging.
  """
  return flask.jsonify(image_list)


@app.route('/results/<image>/<model>')
def results(image, model):
  """
  Return list of features for the specified image and model.
  """
  if image not in image_list:
    return flask.abort(404)
  if model not in model_list:
    return flask.abort(404)
  print(model_list[model])
  if os.path.exists(f"{model_list[model]}/{image}/#{image}_scores.csv"):
    score_list = {}
    with open(f"{model_list[model]}/{image}/#{image}_scores.csv", "r") as f:
      reader = csv.reader(f)
      next(reader, None)
      legends = {row[2]:f"{row[2]} - {float(row[3]):.0%}" for row in reader}
  else:
    legends = {}
    for f in glob.glob(f"{model_list[model]}/{image}_*.tif"):
      name = os.path.basename(f).replace(".tif", "").replace(f"{image}_", "")
      legends[name] = name
  return legends


@app.route('/dzi/<image>.dzi')
def dzi_raw(image):
  """
  Return the Deep Zoom Image (DZI) format for the specified image. This is specific
  to the raw images and is used to enable the zoomable image viewer.
  """
  if image not in image_list:
    return flask.abort(404)
  load_image(image)
  return flask.jsonify({
    "Image": {
      "xmlns": "http://schemas.microsoft.com/deepzoom/2008",
      "Url": f"/dzi/{img['name']}/raw/",
      "Format": "png",
      "Overlap": "0",
      "TileSize": f"{tile_size}",
      "Size": {
        "Height": img["raw"][-1].height,
        "Width": img["raw"][-1].width
      }
    }
  })

@app.route('/dzi/<image>/<model>/<feature>.dzi')
def dzi_feature(image, model, feature):
  """
  Return the Deep Zoom Image (DZI) format for the specified feature. This is specific
  to the extracted images and is used to enable the zoomable image viewer overlay.
  """
  if image not in image_list:
    return flask.abort(404)
  if model not in model_list:
    return flask.abort(404)
  load_image(image, model, feature)
  return flask.jsonify({
    "Image": {
      "xmlns": "http://schemas.microsoft.com/deepzoom/2008",
      "Url": f"/dzi/{img['name']}/extracted/",
      "Format": "png",
      "Overlap": "0",
      "TileSize": f"{tile_size}",
      "Size": {
        "Height": img["extracted"][-1].height,
        "Width": img["extracted"][-1].width
      }
    }
  })

@app.route('/dzi/<image>/<dir>/<level>/<c>_<r>.<fmt>')
def files(image, dir, level, c, r, fmt):
  """
  Return the tile for the specified image
  @param image: the name of the image
  @param dir: either "raw" or "extracted"
  @param level: the zoom level
  @param c: the column of the tile
  @param r: the row of the tile
  """
  if image not in image_list:
    return flask.abort(404)
  load_image(image)
  if not img[dir][-1]:
    return flask.abort(404)
  # make sure only one process is creating the zoomed image
  lock.acquire()
  if not img[dir][int(level)]:
    scale = math.pow(0.5, img["maxlevel"] - int(level) - 1)
    img[dir][int(level)] = img[dir][-1].resize((int(math.ceil(img[dir][-1].width * scale)),
                                                int(math.ceil(img[dir][-1].height * scale))))
  lock.release()

  x = int(c) * tile_size
  y = int(r) * tile_size
  tile = img[dir][int(level)].crop((x, y, x + tile_size, y + tile_size))
  return send_image(tile, transparent=True)

# --------------------------------------------------------------------------------
# PARSE ARGUMENTS AND START SERVICE
# --------------------------------------------------------------------------------
def main():
  parser = argparse.ArgumentParser(description='Convert trainging data to HDF5 files.')
  envvar = os.getenv('RAW_FOLDER', 'data/raw')
  parser.add_argument('-i', '--input', type=pathlib.Path, default=envvar,
                      help=f'folder that contains all raw input (default: {envvar})')
  envvar = os.getenv('MODEL_FOLDER', 'data/models')
  parser.add_argument('-m', '--model', type=pathlib.Path, default=envvar,
                      help=f'folder that contains all model outputs (default: {envvar})')
  envvar = os.getenv('VALIDATION_FOLDER', 'data/validation')
  parser.add_argument('-v', '--validation', type=pathlib.Path, default=envvar,
                      help=f'folder that contains all validation outputs (default: {envvar})')
  envvar = os.getenv('PORT', '9999')
  parser.add_argument('-p', '--port', type=int, default=envvar,
                      help=f'port used by service (default: {envvar})')
  parser.add_argument('-d', '--debug', action='store_true',
                      help=f'enable debug mode, this will run flask in debug mode.')
  args = parser.parse_args()

  # prepare the data
  load_image_list(args.input)
  load_model_list(args.model)

  # start service
  app.run(debug=args.debug, port=args.port)

# --------------------------------------------------------------------------------
if __name__ == '__main__':
  main()
