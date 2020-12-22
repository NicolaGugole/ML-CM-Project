import numpy as np
import utils.get_dataset as dt
from utils.model import Model
from utils.layer import Layer

# ----------------------------------------- MAIN ----------------------------------------- #
print("One day I will be a very smart Artificial Intelligence!")

inp, exp = dt._get_train_data(2)
ohe_inp = [dt._get_one_hot_encoding(i) for i in inp]
exp = [[elem] for elem in exp]

# create model
model = Model()
model._add_layer(Layer(4, "tanh", _input=(17,)))
model._add_layer(Layer(4, "tanh"))
model._add_layer(Layer(1, "tanh"))
model._compile(0.05, "mse", alpha=0.75)
model._train(ohe_inp, exp, batch_size=16, epoch=300)