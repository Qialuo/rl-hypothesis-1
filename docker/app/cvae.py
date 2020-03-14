from gcp_api_wrapper import download_blob, upload_blob, shutdown
from time import sleep 
import os 
import pickle
import numpy as np
import matplotlib.pyplot as plt
from keras.datasets import mnist
from keras.layers import Input, Dense, Lambda, concatenate
from keras.models import Model
from keras import backend as K
from keras import objectives
from keras.utils import to_categorical
from scipy.stats import norm

cgan_data_path = '/dat/cgan-data.pkl'
cgan_data_name = 'cgan-data.pkl'
cgan_model_path = '/dat/cgan-model.h5'
cgan_model_name = 'cgan-model.h5'

if not os.path.isfile(cgan_data_path):
    download_blob(cgan_data_name, cgan_data_path) 
with open(cgan_data_path, 'rb') as f:
    data = pickle.load(f)

class CVAE:
    '''
    Conditional Variational Autoencoder
    '''
    def __init__(self, data_dim, label_dim, latent_dim=10, n_hidden=512, model_path=None, batch_size=100000, n_epoch=50):
        '''
        model_path: If `None`, then initialize an untrained model. Otherwise, load from the path. 
        '''
        ## store args 
        self.data_dim = data_dim 
        self.label_dim = label_dim
        self.latent_dim = latent_dim 
        self.n_hidden = n_hidden 
        self.model_path = model_path 
        self.batch_size = batch_size
        self.n_epoch = n_epoch 
        ## define model 
        self.__init_model()
        if model_path is not None: 
            self.cvae.load_weights(model_path)  
        pass
    
    def __init_model(self):
        '''
        Initializes model, does not load weights. 
        '''
        ## get args 
        data_dim = self.data_dim 
        label_dim = self.label_dim 
        latent_dim = self.latent_dim 
        n_hidden = self.n_hidden 
        batch_size = self.batch_size 
        ## encoder 
        x = Input(shape=(data_dim,)) 
        condition = Input(shape=(label_dim,))
        inputs = concatenate([x, condition]) 
        x_encoded = Dense(n_hidden, activation='relu')(inputs) 
        x_encoded = Dense(n_hidden//2, activation='relu')(x_encoded) 
        x_encoded = Dense(n_hidden//4, activation='relu')(x_encoded) 
        mu = Dense(latent_dim, activation='linear')(x_encoded) 
        log_var = Dense(latent_dim, activation='linear')(x_encoded) 
        ## latent sampler 
        def sampling(args): 
            mu, log_var = args 
            eps = K.random_normal(shape=(batch_size, latent_dim), mean=0., stddev=1.) 
            return mu + K.exp(log_var/2.) * eps 
        ## sample 
        z = Lambda(sampling, output_shape=(latent_dim,))([mu, log_var]) 
        z_cond = concatenate([z, condition]) 
        ## decoder 
        z_decoder1 = Dense(n_hidden//4, activation='relu') 
        z_decoder2 = Dense(n_hidden//2, activation='relu') 
        z_decoder3 = Dense(n_hidden, activation='relu') 
        y_decoder = Dense(data_dim, activation='linear') 
        z_decoded = z_decoder1(z_cond) 
        z_decoded = z_decoder2(z_decoded) 
        z_decoded = z_decoder3(z_decoded) 
        y = y_decoder(z_decoded) 
        ## loss 
        reconstruction_loss = objectives.mean_squared_error(x, y) 
        kl_loss = .5 * K.mean(K.square(mu) + K.exp(log_var) - log_var - 1, axis=-1) 
        cvae_loss = reconstruction_loss + kl_loss 
        ## define full model 
        cvae = Model([x, condition], y) 
        cvae.add_loss(cvae_loss) 
        cvae.compile(optimizer='adam') 
        cvae.summary() 
        self.cvae = cvae 
        ## define encoder model 
        encoder = Model([x, condition], mu) 
        self.encoder = encoder 
        ## define decoder model 
        decoder_input = Input(shape=(latent_dim + label_dim,)) 
        _z_decoded = z_decoder1(decoder_input) 
        _z_decoded = z_decoder2(_z_decoded) 
        _z_decoded = z_decoder3(_z_decoded) 
        _y = y_decoder(_z_decoded) 
        generator = Model(decoder_input, _y) 
        generator.summary() 
        self.generator = generator 
        pass
    
    def __one_hot(self, arr): 
        arr = arr.astype(np.int32) 
        one_hots = np.zeros((arr.size, self.label_dim)) 
        one_hots[np.arange(arr.size), arr] = 1 
        return one_hots
    
    def fit(self):
        ## get args 
        batch_size = self.batch_size 
        n_epoch = self.n_epoch
        ## fit model 
        one_hots = self.one_hot(data[1]) 
        self.cvae.fit([data[0], one_hots],
                shuffle=True,
                epochs=n_epoch, 
                batch_size=batch_size,
                verbose=1)
        pass
    
    def generate(self):
        pass

    def save_model(self, path): 
        self.cvae.save_weights(path) 
    pass

if __name__ == '__main__':
    cvae = CVAE(data_dim=512*2, label_dim=9) 
    cvae.fit() 
    cvae.save_model(cgan_model_path) 
    upload_blob(cgan_model_name, cgan_model_path) 
    while True:
        shutdown()
        sleep(100) 
