import numpy as np # more important than "#include <stdio.h>"
import utils.get_dataset as dt
import copy
import os

from utils.layer import Layer
from utils.model import Model
from utils.plot import Plot
from tqdm import trange
from joblib import Parallel, delayed

class GridSearch:
    def __init__(self):
        self.eta = [0.01]
        self.alpha = [0]
        self._lambda = [0]
        self.batch_size = [1]
        self.models_layers = [] # [[Layers#1], [Layers#2], ...]
        self.lr_decay = [1e-5]
        self.epoch = [300]
        self.weight_range = [(-0.69, 0.69)]

    def _set_parameters(self, **parameters):
        """
            parameters:
                eta : list, 
                alpha : list, 
                _lambda : list, 
                batch_size : list, 
                layers : list of list of Layers,
                lr_decay : list,
                epoch : list,
                weight_range : list of tuple (Lower, Upper)
        """
        if "eta" in parameters:
            self.eta = parameters["eta"]                               # [0.1, 0.0001]
        if "alpha" in parameters:
            self.alpha = parameters["alpha"]                           # [0.6, 0.98]
        if "_lambda" in parameters:
            self._lambda = parameters["_lambda"]                       # [1e-3, 1e-5]
        if "batch_size" in parameters:
            self.batch_size = parameters["batch_size"]                 # [len(inp), 1]
        if "layers" in parameters:
            self.models_layers = parameters["layers"]               
        if "lr_decay" in parameters:
            self.lr_decay = parameters["lr_decay"]                     # [1e-5 1e-6]
        if "epoch" in parameters:
            self.epoch = parameters["epoch"]                           # [100 1000]
        if "weight_range" in parameters:
            self.weight_range = parameters["weight_range"]
    
    def _compute_model_score(self, model_infos):
        # model_infos : (avg_test_acc, (test_acc_bm, vacc_bm, vlossbm, training_bm[(a, va, l, vl)]))
        # test accuracy
        score = 100*model_infos[0] # FOR ML CUP: try to start low and each oscillation will higher the score, then sort decreasingly
        # validation loss smooth and training loss smooth (val has more weight)
        val_loss = []
        train_loss = []
        threashold = 5e-3
        for epoch in model_infos[1][-1]:
            val_loss.append(epoch[3])
            train_loss.append(epoch[2])
        not_decrease_times = 0
        for i in range(len(val_loss)-1):
            if val_loss[i+1] - val_loss[i] > threashold:
                not_decrease_times += 1
        score += not_decrease_times*8

        not_decrease_times = 0
        for i in range(len(train_loss)-1):
            if train_loss[i+1] - train_loss[i] > threashold:
                not_decrease_times += 1
        score += not_decrease_times*2

        return score

    def _train_test_model(self, model, train, train_label, validation, validation_label, batch_size, epoch, decay, test, test_exp):
        train_result = model._train(train, train_label, validation, validation_label, batch_size=batch_size, epoch=epoch, decay=decay)
        test_result = model._infer(test, test_exp)
        return train_result, test_result

    # TODO: add loss function name for model (not hyperparameter) (atm set it as defualt)
    def _run(self, train, train_label, validation, validation_label, test, test_label, familyofmodelsperconfiguration=5):
        print("Generating weights")
        weights_per_configuration = []         # confs: [ weight_range_inits:[ weight_inits: [particular weight matrix]]]
        for configuration in self.models_layers:
            dimensions = [] # [(in, out), (in, out)] for each layer
            for layer in configuration:
                if len(dimensions) == 0:
                    dimensions.append((layer.input[0], layer.nodes))
                else:
                    dimensions.append((dimensions[-1][1], layer.nodes))
            for w_range in self.weight_range:            
                weight_inits = []
                for _ in range(familyofmodelsperconfiguration):
                    weight_init = []
                    for inp,out in dimensions: # for each layer create matrix weight
                        weight_init.append(np.random.uniform(w_range[0], w_range[1], (out, inp)))
                    weight_inits.append(weight_init)
                weights_per_configuration.append(weight_inits)

        # will use range(max(len, 1)) so if any value for whatever list was not provided it will iterate just one time using the default value
        # max is useless but is more clear what happens if the hyperparameter was not considered
        # if missing value the class initialize all the lists to the default value
        # list of tuple (epoch, batch, decay, compiled_model)
        print("Generating models")
        models_configurations = []
        counter = 0
        for i in range(len(weights_per_configuration)):
            for j in range(len(weights_per_configuration[i])):
                for epoch_index in range(max(len(self.epoch), 1)):
                    for batch_size_index in range(max(len(self.batch_size), 1)):
                        for decay_index in range(max(len(self.lr_decay), 1)):
                            for eta_index in range(max(len(self.eta), 1)):
                                for alpha_index in range(max(len(self.alpha), 1)):
                                    for lambda_index in range(max(len(self._lambda), 1)):
                                        # initialize model
                                        model = Model()
                                        weights_matrix = []
                                        for k in range(len(weights_per_configuration[i][j])):
                                            model_layer = self.models_layers[counter//(len(self.weight_range)*familyofmodelsperconfiguration)][k]
                                            layer = Layer(model_layer.nodes, model_layer.activation_function_type, _input=model_layer.input)
                                            model._add_layer(layer)
                                            weights_copy = []
                                            for node_weights in weights_per_configuration[i][j][k]:
                                                weights_copy.append([])
                                                for weight in node_weights:
                                                    weights_copy[-1].append(weight)
                                            weights_matrix.append(weights_copy)
                                        model._compile(eta=self.eta[eta_index], alpha=self.alpha[alpha_index], _lambda=self._lambda[lambda_index], weight_matrix=weights_matrix, isClassification = False)
                                        models_configurations.append((self.epoch[epoch_index], self.batch_size[batch_size_index], self.lr_decay[decay_index], model))
                counter += 1
        print(f"Generated {len(models_configurations)} diffent models.")
        print("Starting Models Analysis")
        models_per_structure = len(models_configurations) // len(self.models_layers)
        configurations_per_model = len(self.epoch)*len(self.batch_size)*len(self.lr_decay)*len(self.eta)*len(self.alpha)*len(self._lambda)

        subprocess_pool_size = min(os.cpu_count(), models_per_structure)
        structures_best_configurations = []
        for i in range(len(self.models_layers)):
            print("Model ", i)
            configuration_test = [0]*configurations_per_model
            configuration_best_model = [None]*configurations_per_model
            models_training_stats = []      # [[(acc, vacc, loss, vloss), (acc, vacc, loss, vloss)], ...]
            models_test_accuracy = []       # [(tacc, vacc, vloss), ...]
            with Parallel(n_jobs=subprocess_pool_size, verbose=10) as processes:
                result = processes(delayed(self._train_test_model)(models_configurations[i*models_per_structure + j][3], train, train_label, validation, validation_label, models_configurations[i*models_per_structure + j][1], models_configurations[i*models_per_structure + j][0], models_configurations[i*models_per_structure + j][2], test, test_label) for j in range(models_per_structure))
            
            for res in result:
                models_training_stats.append(res[0])
                models_test_accuracy.append(res[1])

            for j in range(models_per_structure):
                test_accuracy, best_model_vaccuracy, best_model_vloss = models_test_accuracy[j]
                training_stats = models_training_stats[j]
                
                configuration_test[j%configurations_per_model] += test_accuracy/(len(self.weight_range)*familyofmodelsperconfiguration)
                if configuration_best_model[j%configurations_per_model] is None:
                    configuration_best_model[j%configurations_per_model] = (test_accuracy, best_model_vaccuracy, best_model_vloss, training_stats)
                else: # REMEMBER: WE ARE NOT TALKING ABOUT ACCURACY ANYMORE, WE ARE USING MEE
                    if configuration_best_model[j%configurations_per_model][0] > test_accuracy:
                        configuration_best_model[j%configurations_per_model] = (test_accuracy, best_model_vaccuracy, best_model_vloss, training_stats)
                    elif configuration_best_model[j%configurations_per_model][0] == test_accuracy:
                        if configuration_best_model[j%configurations_per_model][1] > best_model_vaccuracy:
                            configuration_best_model[j%configurations_per_model] = (test_accuracy, best_model_vaccuracy, best_model_vloss, training_stats)
                        elif configuration_best_model[j%configurations_per_model][1] == best_model_vaccuracy:
                            if configuration_best_model[j%configurations_per_model][2] > best_model_vloss:
                                configuration_best_model[j%configurations_per_model] = (test_accuracy, best_model_vaccuracy, best_model_vloss, training_stats)

            configurations_results = []
            for k in range(configurations_per_model):
                configurations_results.append((configuration_test[k], configuration_best_model[k]))
            structures_best_configurations.append(configurations_results)
        
        for i in range(len(structures_best_configurations)):
            print("Structure", i)
            for j in range(len(structures_best_configurations[i])):
                print("Configuration", j)
                print(structures_best_configurations[i][j][0], structures_best_configurations[i][j][1][:-1])

        # evaluate models to find best
        for i in range(len(structures_best_configurations)):
            # i-th model structure
            scores = []
            stats = []
            params = []
            test_eval_metrics = []
            for j in range(len(structures_best_configurations[i])):
                scores.append(self._compute_model_score(structures_best_configurations[i][j]))
                test_eval_metrics.append(structures_best_configurations[i][j][0])
                stats.append(structures_best_configurations[i][j][1][-1])
                params.append(self._get_model_parameters(j,len(structures_best_configurations[i])))

            zipped_triples = sorted(zip(stats, scores, params, test_eval_metrics), key = lambda x : x[1]) # sort everything by decreasing score
            max_len = min(len(zipped_triples), 8) # to only get top best results for visualization sake
            stats  =            [x for x,_,_,_ in zipped_triples[:max_len]]
            scores =            [x for _,x,_,_ in zipped_triples[:max_len]]
            params =            [x for _,_,x,_ in zipped_triples[:max_len]]
            test_eval_metrics = [x for _,_,_,x in zipped_triples[:max_len]]

            for j in range(max_len):
                print(f"Configuration {j}, score : {scores[j]}, test_mee : {test_eval_metrics[j]}, params:{params[j]}")

            Plot._plot_train_stats(stats,title=f"Model {i}", epochs=[x['epoch'] for x in params], block=(i==len(structures_best_configurations)-1), classification=False)

    def _get_model_parameters(self, index, configurations_per_model):
        # ALL THIS IS FOR COMPREHENSION ONLY, TUTTO RIDUCIBILE AD UN CICLO VOLENDO, 5-6 RIGHE MAX TRANQUI EP NO RABIA
        # len(self.epoch)*len(self.batch_size)*len(self.lr_decay)*len(self.eta)*len(self.alpha)*len(self._lambda)
        epoch_len = max(configurations_per_model // len(self.epoch), 1)
        epoch = self.epoch[index // epoch_len]

        index = index % epoch_len # shift inside single epoch
        batch_size_len = max(epoch_len // len(self.batch_size), 1)
        batch_size = self.batch_size[index // batch_size_len]

        index = index % batch_size_len # shift inside single batch_size
        lr_decay_len = max(batch_size_len // len(self.lr_decay), 1)
        lr_decay = self.lr_decay[index // lr_decay_len]

        index = index % lr_decay_len # shift inside single lr_decay
        eta_len = max(lr_decay_len // len(self.eta), 1)
        eta = self.eta[index // eta_len]

        index = index % eta_len # shift inside single eta
        alpha_len = max(eta_len // len(self.alpha), 1)
        alpha = self.alpha[index // alpha_len]

        index = index % alpha_len # shift inside single alpha
        alpha_len = max(alpha_len // len(self.alpha), 1)
        _lambda = self._lambda[index // alpha_len]

        return {'epoch':epoch, 'batch_size':batch_size, 'lr_decay':lr_decay, 'eta':eta, 'alpha':alpha, '_lambda':_lambda}


                                 
if __name__ == "__main__":
    gs = GridSearch()
    train, validation, test, train_labels, validation_labels, test_labels = dt._get_split_cup()
    models = [
        [Layer(8, "tanh", _input=(10,)), Layer(8, "tanh"), Layer(2, "linear")],
        [Layer(8, "leaky_relu", _input=(10,)), Layer(4, "leaky_relu"),Layer(4, "leaky_relu"), Layer(2, "linear")],
        [Layer(8, "leaky_relu", _input=(10,)), Layer(8, "leaky_relu"), Layer(2, "linear")]
    ]
    gs._set_parameters(layers=models, 
                    weight_range=[(-0.69, 0.69)],
                    eta=[1e-4,8e-5,5e-5],
                    alpha=[0.8,0.98],
                    batch_size=[len(train_labels)],
                    epoch=[200],
                    lr_decay=[1e-5],
                    _lambda=[1e-3, 1e-4, 1e-5]
                )
    gs._run(train, train_labels, validation, validation_labels, test, test_labels, familyofmodelsperconfiguration=3)