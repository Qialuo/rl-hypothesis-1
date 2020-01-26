from google.cloud import storage
import os
import random 
import pickle
import numpy as np
from keras.models import Sequential, Model 
from keras.layers import Dense, Flatten
from keras.layers.convolutional import Conv2D

model_path = '/app/transfer-model.h5' 
data_path = '/app/data.pkl'
cgan_data_path = '/app/cgan-data.pkl'
bucket_name = os.environ['BUCKET_NAME'] 

def download_blob(bucket_name, source_blob_name, destination_file_name):
    """Downloads a blob from the bucket."""
    # bucket_name = "your-bucket-name"
    # source_blob_name = "storage-object-name"
    # destination_file_name = "local/path/to/file"

    storage_client = storage.Client.from_service_account_json('/app/service-account.json')

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)

    print(
        "Blob {} downloaded to {}.".format(
            source_blob_name, destination_file_name
        )
    )
    pass

def upload_blob(bucket_name, source_file_name, destination_blob_name):
    """Uploads a file to the bucket."""
    # bucket_name = "your-bucket-name"
    # source_file_name = "local/path/to/file"
    # destination_blob_name = "storage-object-name"

    storage_client = storage.Client.from_service_account_json('/app/service-account.json')
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_filename(source_file_name)

    print(
        "File {} uploaded to {}.".format(
            source_file_name, destination_blob_name
        )
    )
    pass

# download model only if needed 
if not os.path.isfile(model_path): 
    download_blob(bucket_name, 'rl-full.h5-backup', model_path) 
    pass

# download data only if needed 
if not os.path.isfile(data_path): 
    download_blob(bucket_name, 'memory.pkl-backup', data_path) 
    pass

with open(data_path , 'rb') as f: 
    data = pickle.load(f)
    pass 

def build_model(state_size, action_size):
    model = Sequential()
    model.add(Conv2D(32, (8, 8), strides=(4, 4), activation='relu', input_shape=state_size))
    model.add(Conv2D(64, (4, 4), strides=(2, 2), activation='relu'))
    model.add(Conv2D(64, (3, 3), strides=(1, 1), activation='relu'))
    model.add(Flatten())
    model.add(Dense(512, activation='relu'))
    model.add(Dense(action_size))
    model.summary()
    return model

full_model = build_model((84, 84, 4), 3) 
full_model.load_weights(model_path) 

rl_1_dense = Model(inputs=full_model.inputs, outputs=full_model.layers[4].output)
rl_convs = Model(inputs=full_model.inputs, outputs=full_model.layers[3].output)

def _transfer_transform_rl_observation(rl_observation, model=rl_1_dense):
    '''
    Applies a transfer sampling transform. 
    '''
    # state, action, reward, next_state, dead
    rl_observation = list(rl_observation) 
    rl_observation[0] = model.predict(rl_observation[0]) # state 
    rl_observation[3] = model.predict(rl_observation[3]) # next_state 
    return rl_observation 

def _map_reward_dead_to_int(rl_observation): 
    rewarded = rl_observation[2] > .5 
    dead = rl_observation[4] 
    if (not rewarded) and dead: 
        return 0
    elif rewarded and (not dead):
        return 1
    elif (not rewarded) and (not dead):
        return 2
    # rewarded and dead 
    # this should not occur 
    return 3 

def _map_int_to_reward_dead(state_int):
    "returns a (reward, dead) tuple"
    if state_int == 0:
        return 0., True
    elif state_int == 1:
        return 1., False
    elif state_int == 2:
        return 0., False
    # state_int == 3 
    # this should not occur 
    return 1., True 

def _map_transfers_to_array(transfer_transformed_rl_observation):
    transfer_state = transfer_transformed_rl_observation[0] 
    transfer_next_state = transfer_transformed_rl_observation[3] 
    return np.concatenate([transfer_state, transfer_next_state], axis=1) 

def _map_array_to_transfers(transfer_array, split_point=512): 
    "returns state, next_state"
    return transfer_array[:,:split_point], transfer_array[:,split_point:] 

def transfer_sample(n=10000, model=rl_1_dense): 
    '''
    Generates a random list of n RL observations. 
    Transfer sampling is applied. 
    '''
    if n > 0:
        sample = random.sample(data, n) 
    else:
        sample = data
    return list(map(_transfer_transform_rl_observation, sample))

def normalize(ndarray):
    ndarray = np.log1p(ndarray)
    ndarray = ndarray * (ndarray > 0.) # relu
    return ndarray - 3.5

def denormalize(ndarray):
    ndarray = ndarray + 3.5
    ndarray = ndarray * (ndarray > 0.) # relu
    ndarray = np.expm1(ndarray)
    return ndarray

def cgan_sample(n=10000, model=rl_1_dense):
    '''
    Generates a random sample of transformed RL observations.
    Transfer learning transform is applied.
    Data is formatted for cGAN fitting.
    '''
    tr = transfer_sample(n, model)
    labels = np.array(list(map(_map_reward_dead_to_int, tr)))
    states = np.concatenate(list(map(_map_transfers_to_array, tr)))
    states = normalize(states)
    return states, labels

def transform_all_and_upload(model=rl_1_dense): 
    sample_tuple = cgan_sample(n=-1, model=model) 
    with open(cgan_data_path, 'rb') as f: 
        pickle.dump(sample_tuple, f) 
    upload_blob(bucket_name, cgan_data_path, 'cgan-data.pkl') 
    pass 

if __name__ == '__main__':
    transform_all_and_upload() 

