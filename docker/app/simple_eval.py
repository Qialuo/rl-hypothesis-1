
# Before running more-advanced experiments, I want to test for feasibility. 
# In an advanced evaluation, sampling should reflect the automaton's 
# experience, with the GAN being trained on only the observed real data. 
# In this simple evaluation, the GAN will not be trained--I need to 
# justify the engineering work first. The GAN is trained on a single, 
# large dataset. The evaluation will work as follows.
# 1. Sample data, pooling simulants with real. 
# 2. Fit the q-net 
# 3. Generate the metric: average score 

## libraries 
from gcp_api_wrapper import download_blob, upload_blob, shutdown
from cgan import CGAN
from rl import DQNAgent 
from transfer_sampler import inverse_transfer_sample
from keras.layers.advanced_activations import ReLU
from keras.layers import Dense 
from keras.models import Sequential, Model 
from keras.optimizers import Adam
from keras import backend as K 
import os 
import gym
import pickle
import random 
import numpy as np 

## constants 
CGAN_DATA_PATH='/app/cgan-data.pkl'
CGAN_DATA_BLOB_NAME='cgan-data.pkl'
CGAN_MODEL_PATH='/app/cgan-model.h5'
CGAN_MODEL_BLOB_NAME='cgan-model.h5'
FULL_RL_MODEL_PATH='/app/breakout_dqn.h5'  
FULL_RL_MODEL_BLOB_NAME='rl-full.h5'

# ensure files are downloaded 
if not os.path.isfile(CGAN_DATA_PATH): 
    download_blob(CGAN_DATA_BLOB_NAME, CGAN_DATA_PATH) 
if not os.path.isfile(CGAN_MODEL_PATH): 
    download_blob(CGAN_MODEL_BLOB_NAME, CGAN_MODEL_PATH) 
if not os.path.isfile(FULL_RL_MODEL_PATH):
    download_blob(FULL_RL_MODEL_BLOB_NAME, FULL_RL_MODEL_PATH) 

# load files 
with open(CGAN_DATA_PATH, 'rb') as f: 
    CGAN_DATA = pickle.load(f)
CGAN_MODEL = CGAN(load_model_path=CGAN_MODEL_PATH)
FULL_RL_MODEL = DQNAgent(action_size=3, load_model=True) 

def simple_sample(sample_size, probability_simulated): 
    '''
    Generates a mixed dataset of simulated and real embedded samples. 
    Samples are "embedded" because we've used transfer learning. 
    Sampling is "simple" because the GAN is not fit with each simple. 
    '''
    n_fake = np.random.binomial(sample_size, probability_simulated) 
    n_real = sample_size - n_fake 
    ## sample real data 
    real_data = __sample_real_data(n_real) 
    ## sample fake data 
    fake_data = __sample_fake_data(n_fake) 
    ## merge and return 
    real_data = list(real_data)
    fake_data = list(fake_data) 
    return real_data + fake_data 

def fit(data, n_args=3, discount=.99, n_iters=1000, verbose=True):
    '''
    Fits a transfer-learned model on embedded data. Once fit, the 
    abstract model is combined with its lower parts (ie. convolutions) 
    and returned. Metrics are also returned to support later diagnostics. 
    '''
    ## Define model 
    model = Sequential() 
    model.add(ReLU(input_shape=(512,)))
    dense = Dense(n_args) 
    model.add(dense) 
    q_scores = model.output 
    action_ints = K.placeholder(shape=(None,), dtype='int32') 
    y = K.placeholder(shape=(None,), dtype='float32') 
    action_one_hots = K.one_hot(action_ints, n_args) 
    q_scores = K.sum(q_scores * action_one_hots, axis=1) 
    square_error = K.square(y - q_scores) 
    loss = K.mean(square_error)
    updates = Adam(.001, .9).get_updates(loss, model.trainable_weights)
    train = K.function([model.input, action_ints, y], [loss], updates=updates) 
    ## Fit last layer of q-net on data 
    # build inputs from [(s_t, a_t, r_t, s_t+1, d_t)]_t data 
    states = np.array([tpl[0].flatten() for tpl in data]) 
    states = np.reshape(states, (-1, 512)) 
    action_ints = np.array([tpl[1] for tpl in data]) 
    y = np.array([tpl[2] + (1-int(tpl[4]) * discount * np.amax(tpl[3])) for tpl in data]) 
    losses = [] 
    for _ in range(n_iters): 
        # iterate 
        l = train([states, action_ints, y]) 
        losses.append(l[0]) 
        if verbose:
            print('loss: '+str(l[0])) 
    ## Combine with lower transfer-learned layers
    weights = dense.get_weights() 
    FULL_RL_MODEL.last_dense.set_weights(weights) 
    ## Model returned as side-effect. Return loss statistics 
    return losses 

def metric_trials(sample_size = 1000, max_steps=10000): 
    '''
    Metric: Average score  
    '''
    return np.mean([FULL_RL_MODEL.simulate(max_steps=max_steps) for _ in range(sample_size)]) 

def simple_eval_experiment(sample_size, probability_simulated):
    '''
    Generates a single observation for a simple evaluation. 
    args:
     - `sample_size`: number of game transitions to sample. 
     - `probability_simulated`: how many samples are to be GAN-generated? 
    retruns:
     - `metric`: average score over iterated trials 
     - `losses`: model fitting losses, for diagnostics 
    '''
    data = simple_sample(sample_size, probability_simulated) 
    losses = fit(data) 
    metric = metric_trials() 
    return {'metric': metric, 'losses': losses} 

def __sample_real_data(n):
    idx = random.sample(range(CGAN_DATA[1].shape[0]), n) 
    states = CGAN_DATA[0][idx,:] 
    labels = CGAN_DATA[1][idx] 
    return inverse_transfer_sample(states, list(labels)) 

def __sample_fake_data(n):
    '''
    Fake data is generated by a cGAN. Conditioned states are sampled 
    from a choice distribution. 
    '''
    # semi-stratified sampling over `(rewarded and dead)`. 
    # `action` assumed uniformly distributed. 
    labels = np.random.choice([0,1,2,3,4,5,6,7,8], p=[.01/3, .03/3, .96/3]*3, size=n) 
    noise = np.random.normal(0, 1, (n, 100)) 
    fake_data_raw = CGAN_MODEL.generator.predict([noise, labels]) 
    # data needs to be transformed into `(state_t, action_t, reward_t, state_t+1, dead_t)` 
    fake_data = inverse_transfer_sample(fake_data_raw, list(labels)) 
    return fake_data

if __name__ == '__main__':
    from time import sleep 
    while True: 
        sleep(100) # debugging... 
    # TODO 
    pass 















