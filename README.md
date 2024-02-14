# Image Viewer

This program can help you viewing the images generated and compare them with the raw data.

## Installation

You will need to first clone the repository from https://git.ncsa.illinois.edu/criticalmaas/deepzoom

To use the program you will need to install the rquirements. This should be done using a
virtual environment. This can be done on hydro using the following commands:

```bash
cd deepzoom
module load python/3.9.13
python -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
```

## Folders adn Data

The system assumes that the data used as input (`data/raw`) is the map that was segmented and the
results are placed in `data/models/`.

This system can use command line arguments to configure, or it can use the data folder by default.
For example for hydro I have setup my data folder using the following commands:

```bash
cd deepzoom
mkdir -p data/models
ln -s /projects/bbym/shared/data/hackathon_2024-02-12 data/raw
ln -s /projects/bbym/shared/results/6mhack/output data/models/autolabel
ln -s /projects/bbym/shared/results/6mhack_man_labels/output data/models/manlabel
```

## Running

If you want to run this program on hydro you will need to use port forwarding. You will need to run
`ssh -L 9999:localhost:9922 hydro.ncsa.illinois.edu`. Afer login, enable the virtual environment
you created, and you can start the program: `./app.py -p 9922`. Note that the port given to the
application matches the second number in the ssh command.

Since others can run the program it is recommended to pick a port you want to use (which needs to
be greater than 1024) and update your ssh command.

Once you have the application running, you can view it in your browser at https://localhost:9999.
Notice that the port for the URL is the first number in the SSH command.

## Command Line

Using `./app.py -h` will show a brief help text:

```
./app.py -h
usage: app.py [-h] [-i INPUT] [-m MODEL] [-v VALIDATION] [-p PORT] [-d]

Convert trainging data to HDF5 files.

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        folder that contains all raw input (default: data/raw)
  -m MODEL, --model MODEL
                        folder that contains all model outputs (default: data/models)
  -v VALIDATION, --validation VALIDATION
                        folder that contains all validation outputs (default: data/validation)
  -p PORT, --port PORT  port used by service (default: 9999)
  -d, --debug           enable debug mode, this will run flask in debug mode.
  ```