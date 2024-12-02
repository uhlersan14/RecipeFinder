# new terminal
# cd model
# python model.py -u 'MONGO_DB_CONNECTION_STRING'

import argparse

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sn
from pymongo import MongoClient

parser = argparse.ArgumentParser(description='Create Model')
parser.add_argument('-u', '--uri', required=True, help="mongodb uri with username/password")
args = parser.parse_args()

mongo_uri = args.uri
mongo_db = "tracks"
mongo_collection = "tracks"

client = MongoClient(mongo_uri)
db = client[mongo_db]
collection = db[mongo_collection]

# fetch a single document
track = collection.find_one(projection={"gpx": 0, "url": 0, "bounds": 0, "name": 0})
values = [track.values() for track in collection.find(projection={"gpx": 0, "url": 0, "bounds": 0, "name": 0})]

# we later use track document's field names to label the columns of the dataframe
df = pd.DataFrame(columns=track.keys(), data=values).set_index("_id")

df['avg_speed'] = df['length_3d']/df['moving_time']
df['difficulty_num'] = df['difficulty'].map(lambda x: int(x[1])).astype('int32')

# drop na values
df.dropna()
df = df[df['avg_speed'] < 2] # an avg of > 2m/s is probably not a hiking activity
df = df[df['min_elevation'] > 0]
df = df[df['length_2d'] < 100000]

corr = df.corr(numeric_only=True)

print(corr)
sn.heatmap(corr, annot=True)
# plt.show()

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import Normalizer

y = df.reset_index()['moving_time']
x = df.reset_index()[['downhill', 'uphill', 'length_3d', 'max_elevation']]

x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.20, random_state=42)

# Baseline Linear Regression
lr = LinearRegression()
lr.fit(x_train, y_train)

y_pred_lr = lr.predict(x_test)
r2 = r2_score(y_test, y_pred_lr)
mse = mean_squared_error(y_test, y_pred_lr)

# Mean Squared Error / R2
print("r2:\t{}\nMSE: \t{}".format(r2, mse))

# GradientBoostingRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split

gbr = GradientBoostingRegressor(n_estimators=50, random_state=9000)
gbr.fit(x_train, y_train)
y_pred_gbr = gbr.predict(x_test)
r2 = r2_score(y_test, y_pred_gbr)
mse = mean_squared_error(y_test, y_pred_gbr)

print("r2:\t{}\nMSE: \t{}".format(r2, mse))

def din33466(uphill, downhill, distance):
    km = distance / 1000.0
    print(km)
    vertical = downhill / 500.0 + uphill / 300.0
    print(vertical)
    horizontal = km / 4.0
    print(horizontal)
    return 3600.0 * (min(vertical, horizontal) / 2 + max(vertical, horizontal))

def sac(uphill, distance):
    km = distance / 1000.0
    return 3600.0 * (uphill/400.0 + km /4.0)

print("*** DEMO ***")
downhill = 300
uphill = 700
length = 10000
max_elevation = 1200
print("Downhill: " + str(downhill))
print("Uphill: " + str(uphill))
print("Length: " + str(length))
demoinput = [[downhill,uphill,length,max_elevation]]
demodf = pd.DataFrame(columns=['downhill', 'uphill', 'length_3d', 'max_elevation'], data=demoinput)
demooutput = gbr.predict(demodf)
time = demooutput[0]

import datetime

print("DIN: " + str(datetime.timedelta(seconds=din33466(uphill, downhill, length))))
print("SAC: " + str(datetime.timedelta(seconds=sac(uphill, length))))
print("Our Model: " + str(datetime.timedelta(seconds=time)))


# Save To Disk
import pickle

# save the classifier
with open('GradientBoostingRegressor.pkl', 'wb') as fid:
    pickle.dump(gbr, fid)    

# load it again
with open('GradientBoostingRegressor.pkl', 'rb') as fid:
    gbr_loaded = pickle.load(fid)