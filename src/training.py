from error_functions import ErrorFunction
from learning_rate_decay_techniques import LearningRate
from metrics import Metric
from regularizations import Regularizations

import numpy as np
import tqdm as tqdm
import math

class Training:

    def __init__(self, net, error_func, metr, lr, momentum, reg_type, lambda_, lr_decay = None, limit_step = None, decay_rate = None, decay_steps = None):
        self._net = net
        self._error_func = ErrorFunction.init_error_function(error_func) # tuple composed by (error_function, error_function_der, name)
        self._metric_name = metr
        self._metric = Metric.init_metric(metr)
        self.lr = lr
        self.base_lr = self.lr
        self.final_lr = self.base_lr / 100.0
        self.lr_decay = None
        if lr_decay is not None:
            self.lr_decay = LearningRate.init_decay_technique(lr_decay) # decay function for learning rate
        self.limit_step = limit_step
        self.decay_rate = decay_rate
        self.decay_steps = decay_steps
        self.momentum = momentum
        self.lambda_ = lambda_
        self.reg = Regularizations.init_regularization(reg_type) # tuple composed by (reg_function, reg_function_der, name)

    # TODO define all properties for other attributes
    @property
    def lr_params(self):
        """ Returns all the parameters related to the learning rate. Used for the decay """
        return {'lr': self.lr, 'base_lr': self.base_lr, 'final_lr': self.final_lr, 'lr_decay': self.lr_decay,
                'limit_step': self.limit_step, 'decay_rate': self.decay_rate, 'decay_steps': self.decay_steps,
                'staircase': self.staircase, 'curr_lr': self.lr}

    @property
    def net(self):
        return self._net

    @property
    def error_func(self):
        return self._error_func

    @property
    def metr(self):
        return self._metric

    def gradient_descent(self, tr_x, tr_y, val_x, val_y, epochs, batch_size, disable_tqdm=True, **kwargs):
        # TODO copy and paste of optimize method. Modify according to our needs
        """
        :param tr_x: (numpy ndarray) input training set
        :param tr_y: (numpy ndarray) targets for each input training pattern
        :param val_x: (numpy ndarray) input validation set
        :param val_y: (numpy ndarray) targets for each input validation pattern
        :param epochs: (int) number of training epochs
        :param batch_size: (int) number of patterns per single batch
        :param disable_tqdm: True to disable progress bar
        :return: tr_error_values, tr_metric_values, val_error_values, val_metric_values
        """
        # add one dimension to the sets if they are one-dimensional
        tr_x = tr_x[np.newaxis, :] if len(tr_x.shape) < 2 else tr_x
        tr_y = tr_y[np.newaxis, :] if len(tr_y.shape) < 2 else tr_y
        if val_x is not None:
            val_x = val_x[np.newaxis, :] if len(val_x.shape) < 2 else val_x
            val_y = val_y[np.newaxis, :] if len(val_y.shape) < 2 else val_y

        # initialize some variables
        tr_error_values, tr_metric_values, val_error_values, val_metric_values = [], [], [], []
        net = self.net  # just to be shorter
        momentum_net = net.get_empty_struct()
        step = 0

        # cycle through epochs
        for epoch in tqdm.tqdm(range(epochs), desc="Iterating over epochs", disable=disable_tqdm):
            epoch_tr_error = np.zeros(net.layers[-1].n_units)
            epoch_tr_metric = np.zeros(net.layers[-1].n_units)
            # epoch_val_error = np.zeros(net.layers[-1].n_units)
            # epoch_val_metric = np.zeros(net.layers[-1].n_units)

            # shuffle the training set if using mini-batches (or stochastic)
            if batch_size != tr_x.shape[0]:
                indexes = list(range(len(tr_x)))
                np.random.shuffle(indexes)
                tr_x = tr_x[indexes]
                tr_y = tr_y[indexes]
            # cycle through batches
            for batch_index in range(math.ceil(len(tr_x) / batch_size)):
                start = batch_index * batch_size
                end = start + batch_size
                train_batch = tr_x[start: end]
                targets_batch = tr_y[start: end]
                grad_net = net.get_empty_struct()

                # # computes penalty term (regularization)
                # w_tot = []
                # if self.lambda_ != 0:
                #     for layer in net.layers:
                #         w_tot = np.concatenate((w_tot, np.ndarray.flatten(layer.weights)))
                # regularization = [regs[self.reg_type].func(w=w_tot, lambda_=self.lambda_)] * len(epoch_tr_error)

                # cycle through patterns and targets within a batch and accumulate the gradients
                for pattern, target in zip(train_batch, targets_batch):
                    net_outputs = net.forward(inp=pattern)

                    # epoch training error = itself + error_func + regularization
                    epoch_tr_error = np.add(epoch_tr_error, self.error_func[0](prediction=net_outputs, target=target))
                    # epoch_tr_error = np.add(
                    #     np.add(epoch_tr_error, self.error_func.func(predicted=net_outputs, target=target)),
                    #     regularization
                    # )
                    epoch_tr_metric = np.add(epoch_tr_metric, self.metr(prediction=net_outputs, target=target))

                    # set the layers' gradients and add them into grad_net
                    # (emulate pass by reference of grad_net using return and reassign)
                    dErr_dOut = self.error_func[1](prediction=net_outputs, target=target)
                    grad_net = net.backprop(dErr_dOut, grad_net)

                # learning rate decays
                if self.lr_decay is not None:
                    step += 1
                    self.lr = lr_decays[self.lr_decay].func(curr_step=step, **self.lr_params)

                # weights update
                for layer_index in range(len(net.layers)):
                    # grad_net contains the gradients of all the layers (and units) in the network
                    grad_net[layer_index]['weights'] /= batch_size
                    grad_net[layer_index]['biases'] /= batch_size
                    # delta_w is equivalent to lrn_rate * local_grad * input_on_that_connection (local_grad = delta)
                    delta_w = self.lr * grad_net[layer_index]['weights']
                    delta_b = self.lr * grad_net[layer_index]['biases']
                    # momentum_net[layer_index]['weights'] is the new delta_w --> it adds the momentum
                    # Since it acts as delta_w, it multiplies itself by the momentum constant and then adds
                    # lrn_rate * local_grad * input_on_that_connection (i.e. "delta_w")
                    momentum_net[layer_index]['weights'] *= self.momentum
                    momentum_net[layer_index]['biases'] *= self.momentum
                    momentum_net[layer_index]['weights'] = np.add(momentum_net[layer_index]['weights'], delta_w)
                    momentum_net[layer_index]['biases'] = np.add(momentum_net[layer_index]['biases'], delta_b)
                    net.layers[layer_index].weights = np.subtract(
                        np.add(net.layers[layer_index].weights, momentum_net[layer_index]['weights']),
                        self.reg[1](w=net.layers[layer_index].weights, lambda_=self.lambda_),
                    )
                    net.layers[layer_index].biases = np.add(
                        net.layers[layer_index].biases,
                        momentum_net[layer_index]['biases']
                    )

            # validation
            if val_x is not None:
                epoch_val_error, epoch_val_metric = net.evaluate(inp=val_x, targets=val_y, metr=self._metric_name, error_func=self._error_func[2])
                val_error_values.append(epoch_val_error)
                val_metric_values.append(epoch_val_metric)

            epoch_tr_error = np.sum(epoch_tr_error) / len(epoch_tr_error)
            tr_error_values.append(epoch_tr_error / len(tr_x))
            epoch_tr_metric = np.sum(epoch_tr_metric) / len(epoch_tr_metric)
            tr_metric_values.append(epoch_tr_metric / len(tr_x))

        return tr_error_values, tr_metric_values, val_error_values, val_metric_values