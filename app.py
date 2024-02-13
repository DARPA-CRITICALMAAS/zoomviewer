import flask
from PIL import Image
import math
import io
import glob
from os import path
import threading
import csv
import numpy as np

tile_size = 256
Image.MAX_IMAGE_PIXELS = None
debug = False

app = flask.Flask("zoom")

image_list = None
model_list = None

img = {
  "name": None,
  "model": None,
  "feature": None,
  "raw": None,
  "extracted": None,
  "maxlevel": 0
}

lock = threading.Semaphore()

def get_image_list():
  global image_list
  lock.acquire()
  image_list = []
  if not image_list:
    for f in glob.glob(f"data/raw/*.tif"):
      name = path.basename(f)[:-4]
      if name.endswith(".cog"):
        name = name[:-4]
      image_list.append(name)
    image_list.sort(key=str.lower)
  lock.release()
  return image_list

def get_model_list():
  global model_list
  if not model_list:
    model_list = [path.basename(f).replace(".tif", "") for f in glob.glob(f"data/*") if path.isdir(f) and f != "data/raw"]
    model_list.sort(key=str.lower)
  return model_list

def check_path(name, model=None, feature=None):
  # raw image
  if not model or not feature:
    fpath = f"data/raw/{name}.tif"
    if path.exists(fpath):
      return fpath
    fpath = f"data/raw/{name}.cog.tif"
    if path.exists(fpath):
      return fpath
    return None

  # validation results
  fpath = f"data/{model}/{name}/val_{name}_{feature}.tif"
  if path.exists(fpath):
    return fpath

  # extracted image
  fpath = f"data/{model}/{name}/{name}_{feature}.tif"
  if path.exists(fpath):
    return fpath
  fpath = f"data/{model}/{name}_{feature}.tif"
  if path.exists(fpath):
    return fpath
  return None

def load_image(name, model=None, feature=None):
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

@app.route('/')
def home():
  get_image_list()
  get_model_list()
  return flask.render_template("index.html",
                               model_list=model_list,
                               image_list=image_list,
                               debug=str(debug).lower())

@app.route('/js/<name>')
def download_js(name):
  return flask.send_file(f"js/{name}")

@app.route('/images/<name>')
def download_images(name):
  return flask.send_file(f"images/{name}")

@app.route('/dzi')
def images():
  get_image_list()
  return flask.jsonify(image_list)

@app.route('/results/<image>/<model>')
def results(image, model):
  get_image_list()
  if image not in image_list:
    return flask.abort(404)
  if path.exists(f"data/{model}//{image}/#{image}_scores.csv"):
    with open(f"data/{model}//{image}/#{image}_scores.csv", "r") as f:
      reader = csv.reader(f)
      next(reader, None)
      legends = {row[2]:f"{row[2]} - {float(row[3]):.0%}" for row in reader}
  else:
    legends = {}
    for f in glob.glob(f"data/{model}/{image}_*.tif"):
      name = path.basename(f).replace(".tif", "").replace(f"{image}_", "")
      legends[name] = name
  return legends

@app.route('/dzi/<image>.dzi')
def dzi_raw(image):
  get_image_list()
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
  get_image_list()
  if image not in image_list:
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
  get_image_list()
  if image not in image_list:
    return flask.abort(404)
  load_image(image)
  if not img[dir][-1]:
    return flask.abort(404)
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

if __name__ == '__main__':
  app.run(debug=True, port=9999)
