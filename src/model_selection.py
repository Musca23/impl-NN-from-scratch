from scipy.sparse import data
from utility import *
import numpy as np
import tqdm
from net import Network
import json
from joblib import Parallel, delayed
import numpy as np
import os
from collections import OrderedDict
import random
import itertools as it

# TODO implement cross-validation, grid search and random search inside this class
#TODO generate DocString documentation for all methods

# split a dataset into a train and validation set
def holdout_validation(net,path, test_size, error_func, metr, lr, lr_decay=None, limit_step=None, decay_rate=None, decay_steps=None,
            momentum=0., nesterov=False, epochs=1, batch_size=1, strip=0, reg_type='ridge_regression', lambda_=0, disable_tqdm=False):
    if path == "cup":
        dataset, labels, _, _, _ = read_cup(int_ts=True)
        print("cup")
    else:
        rescale = True if net.params['act_functions'][-1] == 'tanh' else False
        dataset, labels = read_monk_dataset(dataset=path, rescale=rescale)

    train_size = int((1 - test_size) * len(dataset))
    train_X, val_X = dataset[:train_size,:], dataset[train_size:,:]
    train_Y, val_Y = labels[:train_size,:], labels[train_size:,:]
    net.compile(error_func=error_func, metr=metr, lr=lr, lr_decay=lr_decay, limit_step=limit_step,
                    decay_rate=decay_rate, decay_steps=decay_steps, momentum=momentum,
                    nesterov=nesterov, reg_type=reg_type, lambda_=lambda_)
    tr_err, tr_metr, val_err, val_metr = net.fit(tr_x=train_X, tr_y=train_Y, val_x=val_X, val_y=val_Y, batch_size=batch_size, epochs=epochs, strip_early_stopping=strip, disable_tqdm=disable_tqdm)
    return tr_err, tr_metr, val_err, val_metr

''' *** K-FOLD CV *** '''

#TODO DocString documentation

#todo: change loss param with error_func for omogeneous notation
def kfold_CV(net, dataset, error_func, metr, lr, path=None, lr_decay=None, limit_step=None, decay_rate=None, decay_steps=None,

            momentum=0., nesterov=False, epochs=1, batch_size=1, strip=0, k_folds=5, reg_type='ridge_regression', lambda_=0,
            disable_tqdms=(True, True), plot=True, verbose=False, **kwargs):
    if dataset == "cup":
        dev_set_x, labels, _, _, _ = read_cup(int_ts=True)
        print("cup")
    else:
        rescale = True if net.params['act_functions'][-1] == 'tanh' else False
        dev_set_x, labels = read_monk_dataset(dataset=dataset, rescale=rescale)

    # split the dataset into folds
    x_folds = np.array(np.array_split(dev_set_x, k_folds), dtype=object)
    y_folds = np.array(np.array_split(labels, k_folds), dtype=object)

    # initialize vectors for plots
    tr_error_values, tr_metric_values = np.zeros(epochs), np.zeros(epochs)
    val_error_values, val_metric_values = np.zeros(epochs), np.zeros(epochs)
    val_metric_per_fold, val_error_per_fold = [], []
    tr_error_per_fold, tr_metric_per_fold = [], []

    # CV cycle
    for i in tqdm.tqdm(range(k_folds), desc='Iterating over folds', disable=disable_tqdms[0]):
        # create validation set and training set using the folds (for one iteration of CV)
        tr_data, tr_targets, val_data, val_targets = sets_from_folds(x_folds, y_folds, val_fold_index=i)

        # compile and fit the model on the current training set and evaluate it on the current validation set
        net.compile(error_func=error_func, metr=metr, lr=lr, lr_decay=lr_decay, limit_step=limit_step,
                    decay_rate=decay_rate, decay_steps=decay_steps, momentum=momentum, nesterov=nesterov,
                    reg_type=reg_type, lambda_=lambda_)
        # warnings.simplefilter("error")
        #TODO decide to keep this catching of exception
        try:
            tr_history = net.fit(tr_x=tr_data, tr_y=tr_targets, val_x=val_data, val_y=val_targets, epochs=epochs,
                                 batch_size=batch_size, strip_early_stopping=strip, disable_tqdm=disable_tqdms[1])
        except Exception as e:
            print(f"{e.__class__.__name__} occurred. Training suppressed.")
            print(e, '\n')
            return

        # metrics for the graph
        # composition of tr_history:
        #   [0] --> training error values for each epoch
        #   [1] --> training metric values for each epoch
        #   [2] --> validation error values for each epoch
        #   [3] --> validation metric values for each epoch
        #   variables useful for plotting
        tr_error_values += tr_history[0]
        tr_metric_values += tr_history[1]
        val_error_values += tr_history[2]
        val_metric_values += tr_history[3]
        # keep last error value for training and validation per fold
        try:
            tr_error_per_fold.append(tr_history[0][-1])
            tr_metric_per_fold.append(tr_history[1][-1])
            val_error_per_fold.append(tr_history[2][-1])
            val_metric_per_fold.append(tr_history[3][-1])
        except TypeError:
            tr_error_per_fold.append(tr_history[0])
            tr_metric_per_fold.append(tr_history[1])
            val_error_per_fold.append(tr_history[2])
            val_metric_per_fold.append(tr_history[3])

        # reset net's weights for the next iteration of CV
        net = Network(**net.params)

    # average the validation results of every fold
    tr_error_values /= k_folds
    tr_metric_values /= k_folds
    val_error_values /= k_folds
    val_metric_values /= k_folds

    # results
    avg_val_err, std_val_err = np.mean(val_error_per_fold), np.std(val_error_per_fold)
    avg_val_metric, std_val_metric = np.mean(val_metric_per_fold), np.std(val_metric_per_fold)
    avg_tr_err, std_tr_err = np.mean(tr_error_per_fold), np.std(tr_error_per_fold)
    avg_tr_metr, std_tr_metr = np.mean(tr_metric_per_fold), np.std(tr_metric_per_fold)

    # print k-fold metrics
    if verbose:
        print("\nScores per fold:")
        for i in range(k_folds):
            print(f"Fold {i + 1}:\nVal Loss: {val_error_per_fold[i]} - Val Metric: {val_metric_per_fold[i]}\n"
                  f"Train Loss: {tr_error_per_fold[i]} - Train Metric: {tr_metric_per_fold[i]}\n{'-' * 62}\n")
        print('\nAverage scores for all folds:')
        print("Val Loss: {} - std:(+/- {})\n"
              "Train Loss: {} - std:(+/- {})\n"
              "Val Metric: {} - std:(+/- {})\n"
              "Train Metric: {} - std(+/- {})\n".format(avg_val_err, std_val_err,
                                                       avg_tr_err, std_tr_err,
                                                       avg_val_metric, std_val_metric,
                                                       avg_tr_metr, std_tr_metr))
    if plot:
        ylim, lbltr, lblval = None, None, None
        if "monk" in dataset:
            ylim, lbltr, lblval = (0., 1.1), "Training", "Validation"
        plot_curves(tr_error_values, val_error_values, tr_metric_values, val_metric_values, path, ylim=ylim,
                    lbltr=lbltr, lblval=lblval)
    return avg_val_err, std_val_err, avg_val_metric, std_val_metric

''' *** USEFUL FUNCTIONS FOR GRID SEARCH *** '''

def randomize_params(base_params, fb_dim, n_config=2):
    """
    Generates combination of random hyperparameters
    :param base_params: parameters on which the random perturbation will be applied
    :param fb_dim: full batch dimension (expressed as a number)
    :param n_config: number of random configurations to be generated for each hyper-parameter
    :return: combos of randomly generated hyper-parameters' values
    """
    n_config -= 1
    rand_params = {}
    for k, v in base_params.items():
        # if the parameter does not have to change
        if k in ('act_functions', 'weights_init', 'decay_rate', 'loss', 'lr_decay', 'metr', 'reg_type', 'staircase',
                 'units_per_layer', 'limits', 'epochs'):
            rand_params[k] = (v,)
        else:
            rand_params[k] = [v]
            for i in range(n_config):
                # generate n_config random value centered in v
                if k == "batch_size":
                    if v == "full":
                        rand_params[k] = ("full",)
                        continue
                    lower = max(v - 15, 1)
                    upper = min(v + 15, fb_dim)
                    value = random.randint(lower, upper)
                    for bs in rand_params[k]:
                        if abs(value - bs) < 5:
                            value = rand_params[k][0]
                    while value in rand_params[k]:
                        lower = max(v - 15, 1)
                        upper = min(v + 15, fb_dim)
                        value = random.randint(lower, upper)
                        for bs in rand_params[k]:
                            if abs(value - bs) < 5:
                                value = rand_params[k][0]
                    rand_params[k].append(value)

                # elif k == "decay_rate":
                #     if v is not None:
                #         lower = max(0., v - 0.2)
                #         upper = min(1., v + 0.2)
                #         rand_params[k].append(random.uniform(lower, upper))
                #     else:
                #         rand_params[k] = (None,)

                elif k in ("limit_step", "decay_steps"):
                    if base_params['lr_decay'] is not None:
                        if v is None or (base_params['lr_decay'] == 'linear' and k == 'decay_steps') or \
                                (base_params['lr_decay'] == 'exponential' and k == 'limit_step'):
                            rand_params[k] = (None,)
                            continue
                        lower = max(1, v - 100)
                        upper = v + 100
                        rand_params[k].append(random.randint(lower, upper))
                    else:
                        rand_params[k] = (v,)

                elif k in ("lambd", "lr"):
                    value = max(0., np.random.normal(loc=v, scale=0.001))
                    for l in rand_params[k]:
                        if abs(value - l) < 0.0005:
                            value = rand_params[k][0]
                    while value in rand_params[k]:
                        value = max(0., np.random.normal(loc=v, scale=0.001))
                        for l in rand_params[k]:
                            if abs(value - l) < 0.0005:
                                value = rand_params[k][0]
                    rand_params[k].append(value)

                # elif k == "limits":
                #     lower, upper = v[0], v[1]
                #     lower = np.random.normal(loc=lower, scale=0.1)
                #     upper = np.random.normal(loc=upper, scale=0.1)
                #     if lower > upper:
                #         aux = lower
                #         lower = upper
                #         upper = aux
                #     rand_params[k].append((lower, upper))

                elif k == "momentum":
                    value = max(0., np.random.normal(loc=v, scale=0.1))
                    for m in rand_params[k]:
                        if abs(value - m) < 0.05:
                            value = rand_params[k][0]
                    while value in rand_params[k] or value > 1.:
                        value = min(1., np.random.normal(loc=v, scale=0.1))
                        for m in rand_params[k]:
                            if abs(value - m) < 0.05:
                                value = rand_params[k][0]
                    rand_params[k].append(value)

    print(rand_params)
    return rand_params

def list_of_combos(param_dict):
    """
    Takes a dictionary with the combinations of params to use in the grid search and creates a list of dictionaries, one
    for each combination (so it's possible to iterate over this list in the GS, instead of having many nested loops)
    :param param_dict: dict{kind_of_param: tuple of all the values of that param to try in the grid search)
    :return: list of dictionaries{kind_of_param: value of that param}
    """
    expected_keys = sorted(['units_per_layer', 'act_functions', 'weights_init', 'bounds', 'momentum', 'batch_size', 'lr', 'error_func',
                            'metr', 'epochs', 'lr_decay', 'decay_rate', 'decay_steps', 'limit_step',
                            'lambda_', 'reg_type'])
    for k in expected_keys:
        if k not in param_dict.keys():
            param_dict[k] = ('ridge_regression',) if k == 'reg_type' else ((0,) if k == 'lambda_' else (None,))
    param_dict = OrderedDict(sorted(param_dict.items()))
    # cartesian product of input iterables (list of tuples)
    combo_list = list(it.product(*(param_dict[k] for k in param_dict.keys())))
    combos = []
    for c in combo_list:
        if len(c[expected_keys.index('units_per_layer')]) == len(c[expected_keys.index('act_functions')]):
            d = {k: c[i] for k, i in zip(expected_keys, range(len(expected_keys)))}
            combos.append(d) # list of dictionaries

    for c in combos:
        if c['lr_decay'] == 'linear_decay':
            c['decay_rate'] = None
            c['decay_steps'] = None
        elif c['lr_decay'] == 'exponential_decay':
            c['limit_step'] = None

    final_combos = []
    for i in range(len(combos) - 1):
        if combos[i] != combos[i + 1]:
            final_combos.append(combos[i])
    return final_combos

def get_best_models(dataset, coarse=False, n_models=1, fn=None):
    """
    Search and select the best models based on the MEE metric and standard deviation
    :param dataset: name of the dataset (used for reading the file containing the results)
    :param coarse: indicates if best models result from a coarse or fine grid search (used for reading the file name)
    :param n_models: number of best models to be returned
    :param fn: file name for reading a specific file for the results (if different from the default)
    :return: best models in term of MEE and standard deviation and their parameters
    """
    file_name = ("coarse_gs_" if coarse else "fine_gs_") + "results_" + dataset + ".json"
    file_name = file_name if fn is None else fn
    with open("../results/" + file_name, 'r') as f:
        data = json.load(f)

    # put the data into apposite lists
    input_dim = 10 if dataset == "cup" else 17
    models, params, errors, std_errors, metrics, std_metrics = [], [], [], [], [], []
    for result in data['results']:
        if result is not None:
            errors.append(round(result[0], 3))
            std_errors.append(round(result[1], 3))
            metrics.append(round(result[2], 3))
            std_metrics.append(round(result[3], 3))

    errors, std_errors = np.array(errors), np.array(std_errors)
    metrics, std_metrics = np.array(metrics), np.array(std_metrics)
    for i in range(n_models):
        # find best metric model and its index
        index_of_best = np.argmin(metrics) if dataset == "cup" else np.argmax(metrics)
        value_of_best = min(metrics) if dataset == "cup" else max(metrics)

        # search elements with the same value
        if len(metrics) > index_of_best + 1:
            indexes = [index_of_best]
            for j in range(index_of_best + 1, len(metrics)):
                if metrics[j] == value_of_best:
                    indexes.append(j)

            std_metr_to_check = std_metrics[indexes]
            value_of_best = min(std_metr_to_check)
            index_of_best = indexes[np.argmin(std_metr_to_check)]
            for j in indexes:
                if std_metrics[j] != value_of_best:
                    indexes.remove(j)

            err_to_check = errors[indexes]
            value_of_best = min(err_to_check)
            index_of_best = indexes[np.argmin(err_to_check)]
            for j in indexes:
                if errors[j] != value_of_best:
                    indexes.remove(j)

            std_err_to_check = std_errors[indexes]
            value_of_best = min(std_err_to_check)
            index_of_best = indexes[np.argmin(std_err_to_check)]
            for j in indexes:
                if std_errors[j] != value_of_best:
                    indexes.remove(j)

        metrics = np.delete(metrics, index_of_best)
        models.append(Network(input_dim=input_dim, **data['params'][index_of_best]))
        params.append(data['params'][index_of_best])

    return models, params

''' *** GRID SEARCH *** '''

def grid_search(dataset, params, coarse=True, n_config=1):
    """
    Performs a grid search over a set of parameters to find the best combination of hyperparameters
    :param dataset: name of the dataset (monks-1, monks-2, monks-3, cup)
    :param params: dictionary with all the values of the params to try in the grid search
    :param coarse: (bool) if True perform a gird search only on the values of 'params'
    :param n_config: (int) number of config to generate for each param in case of NOT coarse grid search
    """
    models = []
    input_dim = 10 if dataset == "cup" else 17

    # In case generate random combinations
    if not coarse:
        params = randomize_params(params, dataset, n_config)

    # generate list of combinations
    param_combos = list_of_combos(params)
    print(f"Total number of trials: {len(param_combos)}")
    for combo in param_combos:
        models.append(Network(input_dim=input_dim, **combo))

    # perform parallelized grid search
    results = Parallel(n_jobs=os.cpu_count(), verbose=50)(delayed(kfold_CV)(
        net=models[i], dataset=dataset, k_folds=5, disable_tqdm=(False, False), interplot=False,
        **param_combos[i]) for i in range(len(param_combos)))

    # do not save models with suppressed training
    #TODO decide to keep these instructions
    for r, p in zip(results, param_combos):
        if r is None:
            results.remove(r)
            param_combos.remove(p)

    # write results on file
    folder_path = "../results/"
    file_name = ("coarse_gs_" if coarse else "fine_gs_") + "results_" + dataset + ".json"
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)
    data = {"params": param_combos, "results": results}
    with open(folder_path + file_name, 'w') as f:
        json.dump(data, f, indent='\t')


