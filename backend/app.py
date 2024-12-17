# set AZURE_STORAGE_CONNECTION_STRING=***
# $env:AZURE_STORAGE_CONNECTION_STRING="***"
# python -m flask --debug run (works also in PowerShell)

import datetime
import os
import pickle
from pathlib import Path

import pandas as pd
from azure.storage.blob import BlobServiceClient
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

# init app, load model from storage
print("*** Init and load model ***")
if 'AZURE_STORAGE_CONNECTION_STRING' in os.environ:
    azureStorageConnectionString = os.environ['AZURE_STORAGE_CONNECTION_STRING']
    blob_service_client = BlobServiceClient.from_connection_string(azureStorageConnectionString)

    print("fetching blob containers...")
    containers = blob_service_client.list_containers(include_metadata=True)
    suffix = max(
        int(container.name.split("-")[-1])
        for container in containers
        if container.name.startswith("hikeplanner-model")
    )
    model_folder = f"hikeplanner-model-{suffix}"
    print(f"using model {model_folder}")
    
    container_client = blob_service_client.get_container_client(model_folder)
    blob_list = container_client.list_blobs()
    blob_name = next(blob.name for blob in blob_list)

    # Download the blob to a local file
    Path("../model").mkdir(parents=True, exist_ok=True)
    download_file_path = os.path.join("../model", "GradientBoostingRegressor.pkl")
    print(f"downloading blob to {download_file_path}")

    with open(file=download_file_path, mode="wb") as download_file:
         download_file.write(container_client.download_blob(blob_name).readall())

else:
    print("CANNOT ACCESS AZURE BLOB STORAGE - Please set AZURE_STORAGE_CONNECTION_STRING. Current env: ")
    print(os.environ)

file_path = Path(".", "../model/", "GradientBoostingRegressor.pkl")
with open(file_path, 'rb') as fid:
    model = pickle.load(fid)

print("*** Sample calculation with model ***")
def din33466(uphill, downhill, distance):
    km = distance / 1000.0
    vertical = downhill / 500.0 + uphill / 300.0
    horizontal = km / 4.0
    return 3600.0 * (min(vertical, horizontal) / 2 + max(vertical, horizontal))

def sac(uphill, downhill, distance):
    km = distance / 1000.0
    return 3600.0 * (uphill/400.0 + km /4.0)

downhill, uphill, length, max_elevation = 300, 700, 10000, 1200
print(f"Downhill: {downhill}, Uphill {uphill}, Length {length}")
demoinput = [[downhill,uphill,length,max_elevation]]
demodf = pd.DataFrame(columns=['downhill', 'uphill', 'length_3d', 'max_elevation'], data=demoinput)
demooutput = model.predict(demodf)
time = demooutput[0]
print("Our Model: " + str(datetime.timedelta(seconds=time)))
print("DIN33466: " + str(datetime.timedelta(seconds=din33466(uphill=uphill, downhill=downhill, distance=length))))
print("SAC: " + str(datetime.timedelta(seconds=sac(uphill=uphill, downhill=downhill, distance=length))))

print("*** Init Flask App ***")
app = Flask(__name__)
cors = CORS(app)
app = Flask(__name__, static_url_path='/', static_folder='../frontend/build')

@app.route("/")
def indexPage():
     return send_file("../frontend/build/index.html")  

@app.route("/api/predict")
def hello_world():
    downhill = request.args.get('downhill', default = 0, type = int)
    uphill = request.args.get('uphill', default = 0, type = int)
    length = request.args.get('length', default = 0, type = int)

    demoinput = [[downhill,uphill,length,0]]
    demodf = pd.DataFrame(columns=['downhill', 'uphill', 'length_3d', 'max_elevation'], data=demoinput)
    demooutput = model.predict(demodf)
    time = demooutput[0]

    return jsonify({
        'time': str(datetime.timedelta(seconds=time)),
        'din33466': str(datetime.timedelta(seconds=din33466(uphill=uphill, downhill=downhill, distance=length))),
        'sac': str(datetime.timedelta(seconds=sac(uphill=uphill, downhill=downhill, distance=length)))
        })