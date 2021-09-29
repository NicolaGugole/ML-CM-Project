import numpy as np
import time
import kernel
from deflected_subgradient import solveDeflected
import matplotlib.pyplot as plt

class SVR:
    """
    class objective is to fully and intuitively handle the functioning of a Support Vector Regression model through few main function calls:
        'constructor' to initialize
        'fit' to train the model
        'predict' to test the model
    """
    def __init__(self, kernel, kernel_args={}, box=1.0, eps=0.1):
        self.kernel = kernel # string identifying model kernel
        self.box = box       # value for the C parameter, constraining the dual representation
        self.eps = eps       # value for epsilon-tube width

        # various parameters possible for kernels
        self.gamma  = kernel_args['gamma'] if 'gamma' in kernel_args else 'scale' 
        self.degree = kernel_args['degree'] if 'degree' in kernel_args else 1
        self.coef   = kernel_args['coef'] if 'coef' in kernel_args else 0
        self.optim_args = None # will save parameters needed for deflected subgradient optimization process
    
    def __str__(self):
        model_as_string = '\n'
        model_as_string += "Kernel: "+self.kernel
        if self.optim_args is not None: # model fit has happened
            if self.kernel == 'linear':
                model_as_string += "\nW: "+str(self.W)
            elif self.kernel == 'rbf':
                model_as_string += "\nGamma: "+str(self.gamma_value)
            elif self.kernel == 'poly':
                model_as_string += "\nGamma: "+str(self.gamma_value)
                model_as_string += "\tDegree: "+str(self.degree)
                model_as_string += "\tCoef: "+str(self.coef)
            elif self.kernel == 'sigmoid':
                model_as_string += "\nGamma: "+str(self.gamma_value)
                model_as_string += "\tCoef: "+str(self.coef)
            model_as_string += "\nIntercept: "+str(self.intercept)
            model_as_string += "\Optim_args: "+str(self.optim_args)
        model_as_string += "\nBox: "+str(self.box)
        return model_as_string

    def fit(self, x, y, optim_args, beta_init=None, precomp_kernel=None, optim_verbose=True, convergence_verbose=False, fit_time=True):
        start = time.time()
        # save input, output and optimization arguments
        self.xs = x
        self.ys = y
        self.optim_args = optim_args

        # it is possible to precompute the kernel beforehand if one desires
        if precomp_kernel is None:
            self.K, self.gamma_value = kernel.get_kernel(self)
        else:
            self.K, self.gamma_value = precomp_kernel[0], precomp_kernel[1]
        
        # it is possible to initialize betas beforehand if one desires (beta is lagrangian variable ensemble, explained in report section 2) 
        beta_init = np.vstack(np.zeros(self.xs.shape[0])) if beta_init is None else beta_init
        optim_args['vareps'] = self.eps if 'vareps' not in optim_args else optim_args['vareps']
        self.beta, self.status, self.history = solveDeflected(beta_init, self.ys, self.K, self.box, optim_args=optim_args, verbose=optim_verbose) # train the model
        self.betas_history = np.array(self.history['lagrangian']) # save the development of betas for optional eps_ins_loss plot
        if convergence_verbose: # plot convergence rate - logaritmic residual error
            _, axs = plt.subplots(2)
            plot_conv_rate = []
            log_residual_error = []
            for i in range(len(self.history['f']) - 1):
                plot_conv_rate.append((self.history['f'][i+1] - self.history['fstar']) / (self.history['f'][i] - self.history['fstar']))
                log_residual_error.append(np.log(np.abs(self.history['f'][i] - self.history['fstar']) / np.abs(self.history['fstar'])))
            axs[0].plot(range(len(plot_conv_rate)), plot_conv_rate)
            axs[0].set_ylabel("CONV_RATE")
            axs[1].plot(range(len(log_residual_error)), log_residual_error)
            axs[1].set_ylabel("LOG_RESIDUAL_ERROR")
            plt.show()
        self.compute_sv() # compute support vectors given the final lagrangian values
        if self.kernel == "linear": # 'linear' kernel prediction method is different from the other kernels
            self.W = np.dot(self.betasv.T, self.sv)
        if fit_time:
            print(f"Fit time: {time.time() - start}, #SV: {len(self.betasv)}")

    # really slow process..
    def plot_loss(self): 
        temp_beta, temp_sv, temp_betasv, temp_intercept = self.beta, self.sv, self.betasv, self.intercept
        loss_vect = []
        for betas in self.betas_history:
            self.beta = betas
            flag = self.compute_sv(plotting=True)
            if not flag:
                continue
            y_pred = [float(self.predict(self.xs[i])) for i in range(len(self.xs))]
            loss_vect.append(self.eps_ins_loss(y_pred, self.ys))
        plt.plot(range(len(loss_vect)),loss_vect)
        plt.show()
        self.beta, self.sv, self.betasv, self.intercept = temp_beta, temp_sv, temp_betasv, temp_intercept

    def compute_sv(self, plotting=False):
        mask = np.logical_or(self.beta > 1e-6, self.beta < -1e-6)
        if True not in mask: # take min and max if no relevant support vector is present
            if plotting:
                return False
            mask = np.logical_or(self.beta == np.max(self.beta), self.beta == np.min(self.beta))

        support = np.vstack(np.vstack(np.arange(len(self.beta)))[mask]) # get array only of support vectors indexes
        x_mask = np.repeat(mask, self.xs.shape[1], axis=1)
        self.sv = self.xs[x_mask].reshape(-1,self.xs.shape[1]) # get array of support vectors
        y_sv = np.vstack(self.ys.reshape(-1,1)[mask]) # mask out the output values relative to support vectors
        self.betasv = np.vstack(self.beta[mask])
        self.intercept = 0
        # the following operation is possible with any support vector, averaging gives more robustness
        for i in range(self.betasv.size):
            self.intercept += y_sv[i]
            for j in range(self.beta.size):
                self.intercept -= self.beta[j] * self.K[j, support[i]]
        self.intercept /= self.betasv.size # average bias
        self.intercept -= self.eps # -eps -eps -eps
        return True
    
    def predict(self, x):
        x = np.array([x]) # x is test input
        if self.kernel == 'linear':
            # linear prediction is treated differently
            prediction = np.dot(self.W, x.T) + self.intercept
            return prediction

        # TODO discuss with ep
        # if isinstance(self.gamma, str):
        #     gamma = 1/(self.sv.shape[1]*self.sv.var()) if self.gamma == "scale" else 1/(self.sv.shape[1])
        # else:
        #     gamma = self.gamma
        gamma = self.gamma_value # why not?!

        # predict accordingly to the kernel
        if self.kernel == 'rbf':
            K, _ = kernel.rbf(self.sv, x, gamma)
        elif self.kernel == 'poly':
            K, _ = kernel.poly(self.sv, x, gamma, self.degree, self.coef)
        elif self.kernel == 'sigmoid':
            K, _ = kernel.sigmoid(self.sv, x, gamma, self.coef)
        prediction = np.dot(self.betasv.T, K) + self.intercept
        return prediction

    def eps_ins_loss(self, y, y_pred):
        # calculate loss value given ground truth and predicted output
        loss = 0
        for i in range(len(y)):
            loss += (abs(y[i]-y_pred[i]) - self.eps)**2 if abs(y[i]-y_pred[i]) > self.eps else 0
        return loss


# get table of best results per kernel
# get plots of conv rate and log residual
# talk about the dataset, how experiments were carried on, what results we expect, results we actually get and analysis, timings. Comparison with baseline