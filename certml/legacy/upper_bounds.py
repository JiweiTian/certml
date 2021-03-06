"""Determine Upper Bounds"""

import numpy as np
from scipy.linalg import orth
import scipy.sparse as sparse
from sklearn import svm
import cvxpy as cvx


# Migrated
def hinge_loss(w, b, X, Y, sample_weights=None):
    """ Calculate Hinge Loss

    Calculates the hinge loss.

    Parameters
    ----------
    w : np.ndarray of shape (dimensions,)
        Coefficients
    b : float
        Intercept
    X : np.ndarray of shape (instances, dimensions)
        Input Features
    Y : np.ndarray of shape (instances,)
        Input Labels
    sample_weights : None or np.ndarray of shape (???)
        ???

    Returns
    -------
    loss : float
        Hinge loss
    """
    if sample_weights is not None:
        sample_weights = sample_weights / np.sum(sample_weights)
        return np.sum(sample_weights * (np.maximum(1 - Y * (X.dot(w) + b), 0)))
    else:
        return np.mean(np.maximum(1 - Y * (X.dot(w) + b), 0))


# Migrated
def hinge_grad(w, b, X, Y):
    """ Gradient of Hinge Loss

    Parameters
    ----------
    w : np.ndarray of shape (dimensions,)
        Coefficients
    b : float
        Intercept
    X : np.ndarray of shape (instances, dimensions)
        Input Features
    Y : np.ndarray of shape (instances,)
        Input Labels

    Returns
    -------
    grad_w : np.ndarray of shape (dimensions,)
        Gradient of coefficients
    grad_b : float
        Gradient of intercept
    """
    margins = Y * (X.dot(w) + b)
    sv_indicators = margins < 1
    if sparse.issparse(X):
        grad_w = np.sum( 
            -sparse.diags(np.reshape(Y[sv_indicators], (-1))).dot(
                X[sv_indicators, :]) , axis=0) / X.shape[0]
        grad_w = np.array(grad_w).reshape(-1)    
    else:
        grad_w = np.sum( 
            -np.reshape(Y[sv_indicators], (-1, 1)) * X[sv_indicators, :],
             axis=0) / X.shape[0]
    
    grad_b = np.sum( -np.reshape(Y[sv_indicators], (-1, 1))) / X.shape[0]
    
    return grad_w, grad_b


def sample_lower_bound_attack(X_train, Y_train, x_bs, y_bs, epsilon, num_iter_to_throw_out):
    """ Create Poisoned Dataset from Pool of Malicious Data

    Note that the clean and poisoned data order is not randomized.

    Parameters
    ----------
    X_train : np.ndarray of shape (instances, dimensions)
        Clean input features
    Y_train : np.ndarray of shape (instances,)
        Clean input labels
    x_bs : np.ndarray of shape (instances, dimensions)
        Pool of malicious input features
    y_bs : np.ndarray of shape (instances,)
        Pool of malicious input labels
    epsilon : float
        Desired fraction of malicious data to add
    num_iter_to_throw_out : int
        ???

    Returns
    -------
    X_modified : np.ndarray of shape (instances, dimensions)
        Poisoned features
    Y_modified : no.ndarray of shape (instances,)
        Poisoned labels
    idx_train : np.ndarray of shape (instances,)
        Indices of clean and poisoned data
    idx_poison : np.ndarray of shape (instances,)
        Indices of clean and poisoned data
    """
    assert x_bs.shape[0] == y_bs.shape[0]
    num_iter = x_bs.shape[0] - num_iter_to_throw_out

    idx_to_sample = np.random.choice(
        num_iter, 
        size=int(np.round(epsilon * X_train.shape[0])),
        replace=False) + num_iter_to_throw_out

    if sparse.issparse(X_train):
        X_modified = np.concatenate((X_train.toarray(), x_bs[idx_to_sample, :]), axis=0)
    else:
        X_modified = np.concatenate((X_train, x_bs[idx_to_sample, :]), axis=0)

    Y_modified = np.concatenate((Y_train, y_bs[idx_to_sample]))

    idx_train = slice(0, X_train.shape[0])
    idx_poison = slice(X_train.shape[0], X_modified.shape[0])

    return X_modified, Y_modified, idx_train, idx_poison


# Migrated
def svm_with_rho_squared(X_train, Y_train, X_test, Y_test, upper_params_norm_sq, use_bias, 
                         weight_decay=None):
    """ Train Support Vector Machine

    Trains an SVM that has params with squared norm roughly equals (and no larger) than
    upper_params_norm_sq. It works by doing binary search on the weight_decay.

    Parameters
    ----------
    X_train : np.ndarray of shape (instances, dimensions)
        Input training features
    Y_train : np.ndarray of shape (instances,)
        Input training labels
    X_test : np.ndarray of shape (instances, dimensions)
        Input testing features
    Y_test : np.ndarray of shape (instances)
        Input testing labels
    upper_params_norm_sq : ???
    use_bias : ???
    weight_decay : float

    Returns
    -------
    train_loss : float
        Training loss
    train_acc : float
        Training accuracy
    test_loss : float
        Testing loss
    test_acc : float
        Testing accuracu
    params_norm_sq : ???
    weight_decay : ???
    params : np.ndarray of shape (dimensions,)
        Fit coefficients
    bias : float
        Fit intercept
    svm_model : ???
        Trained Support Vector Machine model

    """
    rho_sq_tol = 0.01
    params_norm_sq = None

    if weight_decay is None:
        lower_wd_bound = 0.001
        upper_wd_bound = 256.0
    else:
        lower_wd_bound = 0.001
        upper_wd_bound = 2 * (weight_decay) - lower_wd_bound
        if upper_wd_bound < lower_wd_bound:
            upper_wd_bound = lower_wd_bound

    lower_weight_decay = lower_wd_bound
    upper_weight_decay = upper_wd_bound
    weight_decay = (upper_weight_decay + lower_weight_decay) / 2

    while (
      (params_norm_sq is None) or 
      (upper_params_norm_sq > params_norm_sq) or 
      (np.abs(upper_params_norm_sq - params_norm_sq) > rho_sq_tol)):

        print('Trying weight_decay %s..' % weight_decay)

        C = 1.0 / (X_train.shape[0] * weight_decay)        
        svm_model = svm.LinearSVC(
            C=C,
            tol=1e-6,
            loss='hinge',
            fit_intercept=use_bias,
            random_state=24,
            max_iter=100000,
            verbose=True)
        svm_model.fit(X_train, Y_train)

        params = np.reshape(svm_model.coef_, -1)
        bias = svm_model.intercept_[0]
        params_norm_sq = np.linalg.norm(params)**2 + bias**2

        if upper_params_norm_sq is None:
            break

        print('Current params norm sq = %s. Target = %s.' % (params_norm_sq, upper_params_norm_sq))
        # Current params are too small; need to make them bigger
        # So we should reduce weight_decay
        if upper_params_norm_sq > params_norm_sq:
            upper_weight_decay = weight_decay

            # And if we are too close to the lower bound, we give up
            if weight_decay < lower_wd_bound + 1e-5:
                print('Too close to lower bound, breaking')                
                break

        # Current params are too big; need to make them smaller
        # So we should increase weight_decay
        else:
            lower_weight_decay = weight_decay

            # And if we are already too close to the upper bound, we should bump up the upper bound
            if weight_decay > upper_wd_bound - 1e-5:
                upper_wd_bound *= 2
                upper_weight_decay *= 2       

        if (
          (upper_params_norm_sq > params_norm_sq) or 
          (np.abs(upper_params_norm_sq - params_norm_sq) > rho_sq_tol)):
            weight_decay = (upper_weight_decay + lower_weight_decay) / 2

    train_loss = hinge_loss(params, bias, X_train, Y_train)
    test_loss = hinge_loss(params, bias, X_test, Y_test)

    train_acc = svm_model.score(X_train, Y_train)
    test_acc = svm_model.score(X_test, Y_test)

    print('  Train loss             : ', train_loss)
    print('  Train acc              : ', train_acc)
    print('  Test loss              : ', test_loss)
    print('  Test acc               : ', test_acc)
    print('  Sq norm of params+bias : ', params_norm_sq)

    print('\n')

    return train_loss, train_acc, test_loss, test_acc, params_norm_sq, weight_decay, \
      params, bias, svm_model


def evaluate_attack(X_modified, Y_modified, X_test, Y_test, 
                    idx_train, idx_poison, 
                    epsilon, weight_decay,
                    upper_params_norm_sq,
                    use_bias):
    """ Evaluate Attack

    Trains an SVM on the clean+poisoned data (by calling svm_with_rho_squared)
    and then reports statistics on clean vs poisoned loss, etc.

    Parameters
    ----------
    X_modified : np.ndarray of shape (instances, dimensions)
        Poisoned features
    Y_modified : np.ndarray of shape (instances,)
        Poisoned labels
    X_test : np.ndarray of shape (instances, dimensions)
        Testing features
    Y_test : np.ndarray of shape (instances,)
        Testing labels
    idx_train : np.ndarray of shape (instances,)
        ??
    idx_poison : np.ndarray of shape (instances,)
        Indices of malicious samples in the poisoned dataset
    epsilon : float
        Fraction of data to keep
    weight_decay : float
        Used to set SVM free parameters # TODO Clarify
    upper_params_norm_sq : float
        Used to set SVM free parameters TODO Clarify
    use_bias : bool
        Use bias in the SVM model

    Returns
    -------
    total_train_loss : float
        Training loss on the poisoned dataset due to both clean and malicious data.
    avg_good_train_loss : float
        Training loss on only clean data.
    avg_bad_train_loss : float
        Training loss on only malicious data.
    test_loss : float
        Testing loss.
    overall_train_acc : float
        Training data accuracy on poisoned dataset due to both clean and malicious data.
    good_train_acc : float
        Training data accuracy on only clean data.
    bad_train_acc : float
        Training data accuracy on only malicious data.
    test_acc : float
        Testing data accuracy
    params_norm_sq : float
        Usef to determine SVM C # TODO Clarify
    weight_decay : float
        Used to determine SVM C # TODO Clarify
    """
    X_train = X_modified[idx_train, :]
    Y_train = Y_modified[idx_train]
    X_poison = X_modified[idx_poison, :]
    Y_poison = Y_modified[idx_poison]

    _, _, _, _, _, weight_decay, params, bias, svm_model = \
      svm_with_rho_squared(
        X_modified, Y_modified, 
        X_test, Y_test, 
        upper_params_norm_sq, 
        use_bias, 
        weight_decay)

    new_params = np.reshape(svm_model.coef_, -1)
    new_bias = svm_model.intercept_[0]

    avg_bad_train_loss = hinge_loss(
        new_params, 
        new_bias,
        X_poison,
        Y_poison)
    avg_good_train_loss = hinge_loss(
        new_params, 
        new_bias,
        X_train,
        Y_train)
    params_norm_sq = np.linalg.norm(new_params)**2 + new_bias**2
    total_train_loss = (
        hinge_loss(
            new_params, 
            new_bias, 
            X_modified, 
            Y_modified)) * (1 + epsilon)

    overall_train_acc = svm_model.score(X_modified, Y_modified)
    bad_train_acc = svm_model.score(X_poison, Y_poison)
    good_train_acc = svm_model.score(X_train, Y_train)
    test_acc = svm_model.score(X_test, Y_test)
    test_loss = hinge_loss(new_params, new_bias, X_test, Y_test)


    print('Lower bound:')
    print('  Overall train loss (w/o reg)    : ', total_train_loss)
    print('')
    print('  Overall train acc      : ', overall_train_acc)
    print('  Avg train loss (bad)   : ', avg_bad_train_loss)
    print('  Train acc (bad)        : ', bad_train_acc)
    print('  Avg train loss (clean) : ', avg_good_train_loss)
    print('  Train acc (clean)      : ', good_train_acc)
    print('  Sq norm of params+bias : ', params_norm_sq)
    print('  Test loss              : ', test_loss)
    print('  Test acc               : ', test_acc)
    print('\n')

    return total_train_loss, avg_good_train_loss, avg_bad_train_loss, test_loss, \
           overall_train_acc, good_train_acc, bad_train_acc, test_acc, \
           params_norm_sq, weight_decay


def generate_upper_and_lower_bounds(
    X_train, Y_train,
    norm_sq_constraint, 
    epsilon,
    max_iter,
    num_iter_to_throw_out,
    learning_rate,
    init_w, init_b,
    class_map, centroids, centroid_vec, 
    sphere_radii, slab_radii,
    minimizer,
    verbose=True,
    print_interval=500,
    ):
    """ Generate Upper and Lower Bounds

    Parameters
    ----------
    X_train : :obj:'np.ndarray' of shape (instances, dimensions)
    Y_train : np.ndarray of shape (instances,)
    norm_sq_constraint : float
    epsilon : float
    max_iter : int
    num_iter_to_throw_out : int
    learning_rate : float
    init_w : np.ndarray of shape (dimensions)
    init_b : float
    class_map : dict
    centroids : np.ndarray of shape (classes, dimensions)
    centroid_vec : np.ndarray of shape (1, dimensions)
    sphere_radii : np.ndarray of shape (classes,)
    slab_radii : np.ndarray of shape (classes,)
    minimizer : Minimizer
    verbose : bool
    print_interval : int

    Returns
    -------
    X_modified : np.ndarray of shape (instances, dimensions)
    Y_modified : np.ndarray of shape (instances,)
    idx_train : np.ndarray of shape (instances,)
    idx_poison : np.ndarray of shape (instances,)
    best_upper_bound : float
    best_upper_good_loss : float
    best_upper_bad_loss : float
    best_upper_good_acc : float
    best_upper_bad_acc : float
    best_upper_params_norm_sq :float
    """

    # Initialize Variables as 0
    x_bs = np.zeros((max_iter, X_train.shape[1]))
    y_bs = np.zeros(max_iter)
    sum_w = np.zeros(X_train.shape[1])

    ##########
    # Line 1 #
    ##########

    # Initialize Sum of Gradients (z)
    sum_of_grads_w_sq = np.ones(X_train.shape[1])
    sum_of_grads_w = np.zeros(X_train.shape[1])
    sum_of_grads_b = 0

    # Initialize Upper Bound (U*)
    best_upper_bound = 10000

    # Initialize ??? (\lambda)
    current_lambda = 1 / learning_rate

    # Initialize Model (\theta)
    w = init_w
    b = init_b

    ##########
    # Line 2 #
    ##########

    for iter_idx in range(max_iter):

        #####################
        # Line 5 (1st Half) #
        #####################

        # Calculate gradient of loss
        grad_w, grad_b = hinge_grad(w, b, X_train, Y_train)

        if verbose: 
            if iter_idx % print_interval == 0:
                print("At iter %s:" % iter_idx)

        ##########
        # Line 3 #
        ##########

        # Find the attack point that maximizes loss function.
        # We do not know which class gives the maximum loss.
        # Pick the class with the worse (more negative) margin.
        worst_margin = None
        for y_b in set(Y_train):

            class_idx = class_map[y_b]
            x_b = minimizer.minimize_over_feasible_set(
                y_b, 
                w, 
                centroids[class_idx, :], 
                centroid_vec, 
                sphere_radii[class_idx], 
                slab_radii[class_idx])

            margin = y_b * (w.dot(x_b) + b)
            if (worst_margin is None) or (margin < worst_margin):
                worst_margin = margin
                worst_y_b = y_b
                worst_x_b = x_b

        #####################
        # Line 5 (2nd Half) #
        #####################

        # Take the gradient with respect to that y
        if worst_margin < 1:
            grad_w -= epsilon * worst_y_b * worst_x_b
            grad_b -= epsilon * worst_y_b

        #####################
        # Line 4 (2nd Half) #
        #####################

        # Loss due to malicious data
        bad_loss = hinge_loss(w, b, worst_x_b, worst_y_b)        
        
        # Store iterate to construct matching lower bound
        x_bs[iter_idx, :] = worst_x_b
        y_bs[iter_idx] = worst_y_b

        #####################
        # Line 4 (1st Half) #
        #####################

        # Loss due to clean data
        good_loss = hinge_loss(w, b, X_train, Y_train)
        params_norm_sq = (np.linalg.norm(w)**2 + b**2)

        # Total Loss of the Poisoned Dataset
        total_loss = good_loss + epsilon * bad_loss

        if best_upper_bound > total_loss:
            best_upper_bound = total_loss            
            best_upper_good_loss = good_loss
            best_upper_bad_loss = bad_loss
            best_upper_params_norm_sq = params_norm_sq
            best_upper_good_acc = np.mean((Y_train * (X_train.dot(w) + b)) > 0)
            if worst_margin > 0:
                best_upper_bad_acc = 1.0
            else: 
                best_upper_bad_acc = 0.0            
            
        if verbose: 
            if iter_idx % print_interval == 0:
                print("  Bad margin (%s)         : %s" % (worst_y_b, worst_margin))
                print("  Bad loss (%s)           : %s" % (worst_y_b, bad_loss))                
                print("  Good loss               : %s" % good_loss)
                print("  Total loss              : %s" % total_loss)                
                print("  Sq norm of params_bias  : %s" % params_norm_sq)        
                print("  Grad w norm             : %s" % np.linalg.norm(grad_w))

        ##########
        # Line 6 #
        ##########

        # Update Gradient (z[t] = z[t-1] - g[t])
        sum_of_grads_w -= grad_w
        sum_of_grads_b -= grad_b

        # Update ?? (\lambda[t] = max(...))
        candidate_lambda = np.sqrt(np.linalg.norm(sum_of_grads_w)**2 + sum_of_grads_b**2) / np.sqrt(norm_sq_constraint)
        if candidate_lambda > current_lambda:
            current_lambda = candidate_lambda            

        # Update Model (\theta[t] = z[t] / \lambda[t])
        w = sum_of_grads_w / current_lambda
        b = sum_of_grads_b / current_lambda

    print('Optimization run for %s iterations' % max_iter)

    print('Final upper bound:')
    print("  Total loss              : %s" % best_upper_bound)
    print('')

    # Determine Lower Bound from Candidate Attack Points
    X_modified, Y_modified, idx_train, idx_poison = sample_lower_bound_attack(
        X_train, Y_train, 
        x_bs, y_bs, 
        epsilon, 
        num_iter_to_throw_out)

    return X_modified, Y_modified, idx_train, idx_poison, \
      best_upper_bound, \
      best_upper_good_loss, best_upper_bad_loss, \
      best_upper_good_acc, best_upper_bad_acc, \
      best_upper_params_norm_sq

###################
# Minimizer / CVX #
###################


def cvx_dot(a, b):
    """ CVX Dot Product

    Parameters
    ----------
    a : ???
    b : ???

    Returns
    -------
    dot : ???
        Dot product of a and b
    """
    return cvx.sum_entries(cvx.mul_elemwise(a, b))


def get_projection_matrix(w, centroid, centroid_vec):
    """ Get Projection Matrix

    Parameters
    ----------
    w : np.ndarray of shape (dimensions,)
    centroid : np.ndarray of shape (classes, dimensions)
    centroid_vec : np.ndarray of shape (dimensions,)

    Returns
    -------
    P : np.ndarray of shape (3, dimensions)
        Projection matrix that projects a vector onto the subspace spanned by
            w, centroid, and centroid_vec
    """
    subspace = np.concatenate((
        w.reshape(1, -1),
        centroid.reshape(1, -1),
        centroid_vec.reshape(1, -1)),
        axis=0)
    P = orth(subspace.T).T
    while P.shape[0] < 3:
        P = np.concatenate((P, np.random.normal(size=(1, P.shape[1]))), axis=0)
        P = orth(P.T).T

    return P


class Minimizer(object):
    """ CVX Minimizer / Data Maximizer

    This class determines the attack point the maximises the
    loss constrained by the feasible set. This is the first
    line of the loop in Algorithm 1.

    For the sphere defense this is the optimization problem:

    .. math
        max_x &  1 - y w^T x
        s.t.  &  || x - c ||2 < r

    For the slab defense this is the optimization problem:

    .. math
        max_x & 1 - y w^T x
        s.t.  &  |<x - c, c_vec>| < r

    where
        c :      class centroid
        c_vec :  vector between the two class centroids
    """

    def __init__(self, use_sphere=True, use_slab=True):
        """ Minimizer CVX Minimizer / Data Maximizer

        Parameters
        ----------
        use_sphere : bool
            Use sphere projection?
        use_slab : bool
            Use slab projection?
        """

        d = 3

        self.cvx_x = cvx.Variable(d)
        self.cvx_y = cvx.Parameter(1)        
        self.cvx_w = cvx.Parameter(d)
        self.cvx_centroid = cvx.Parameter(d)
        self.cvx_centroid_vec = cvx.Parameter(d)
        self.cvx_sphere_radius = cvx.Parameter(1)
        self.cvx_slab_radius = cvx.Parameter(1)

        self.cvx_x_c = self.cvx_x - self.cvx_centroid

        self.constraints = []
        if use_sphere:
            self.constraints.append(cvx.norm(self.cvx_x_c, 2) < self.cvx_sphere_radius)
        if use_slab:
            self.constraints.append(cvx.abs(cvx_dot(self.cvx_centroid_vec, self.cvx_x_c)) < self.cvx_slab_radius)

        self.objective = cvx.Maximize(1 - self.cvx_y * cvx_dot(self.cvx_w, self.cvx_x))

        self.prob = cvx.Problem(self.objective, self.constraints)

    def minimize_over_feasible_set(self, y, w, centroid, centroid_vec, sphere_radius, slab_radius,
                                   verbose=False):
        """ Minimize over Feasible Set

        Includes both sphere and slab.

        Parameters
        ----------
        y : int
            Input label
        w : np.ndarray of shape (dimensions,)
            Coefficient
        centroid : np.ndarray of shape (classes, dimensions)
            Centroid for each class
        centroid_vec : np.ndarray of shape (dimensions,)
            Vector between the two centroids
        sphere_radius : np.ndarray of shape (classes,)
            Sphere radius for each class
        slab_radius : np.ndarray of shape (classes,)
            Slab radius for each class
        verbose : bool
            CVX verbose

        Returns
        -------
        x : np.ndarray
            Optimal x;
        """
        P = get_projection_matrix(w, centroid, centroid_vec)
        
        self.cvx_y.value = y
        self.cvx_w.value = P.dot(w.reshape(-1))
        self.cvx_centroid.value = P.dot(centroid.reshape(-1))
        self.cvx_centroid_vec.value = P.dot(centroid_vec.reshape(-1))
        self.cvx_sphere_radius.value = sphere_radius
        self.cvx_slab_radius.value = slab_radius

        self.prob.solve(verbose=verbose)

        x_opt = np.array(self.cvx_x.value).reshape(-1)
        
        return x_opt.dot(P)


class NearestPointFinder(object):
    """ Nearest Point Finder

    We can speed this up by expressing the constraints in one dimension,
    but let's see how it goes first.

    Solve the optimization problem:

    """

    def __init__(self, d):
        """ Nearest Point Finder

        Parameters
        ----------
        d : ???
            ???
        """

        self.cvx_c = cvx.Variable(1)
        self.cvx_y = cvx.Parameter(1)
        self.cvx_g = cvx.Parameter(d)        
        self.cvx_theta = cvx.Parameter(d)
        self.cvx_centroid = cvx.Parameter(d)
        self.cvx_centroid_vec = cvx.Parameter(d)
        self.cvx_sphere_radius = cvx.Parameter(1)
        self.cvx_slab_radius = cvx.Parameter(1)

        # want grad of poisoned point = -g
        # grad of point (cyg, y) = -cg
        # so we want to find c > 0 such that n_poison/n * -cg = -g with 0 < n_poison as low as possible 
        # and (cyg, y) in the feasible set.
        # since n_poison/n > 0, c must > 0. Then n_poison/n = 1/c, 
        # so we want c to be as large as possible.
        # As a sanity check, we know that g itself is in conv(feasible set of gradients).
        # We can hope that either (-g, 1) or (g, -1) is in the feasible set of inputs,
        # because the gradients at each of those points is g
        # so if we let c = -1 then this should work.

        self.cvx_x = self.cvx_c * self.cvx_y * self.cvx_g
        self.cvx_x_c = self.cvx_x - self.cvx_centroid
        self.constraints = [
            cvx.norm(self.cvx_x_c, 2) < self.cvx_sphere_radius, 
            cvx.abs(cvx_dot(self.cvx_centroid_vec, self.cvx_x_c)) < self.cvx_slab_radius,
            self.cvx_y * cvx_dot(self.cvx_theta, self.cvx_x) < 1,
            self.cvx_c > 0]

        self.objective = cvx.Maximize(self.cvx_c)

        self.prob = cvx.Problem(self.objective, self.constraints)

    def find_nearest_point(self, y, g, theta, 
                           centroid, centroid_vec, sphere_radius, slab_radius,
                           verbose=False):
        """ Find Nearest Point

        Parameters
        ----------
        y : int
        g : ??
        theta :
        centroid : np.ndarray of shape (classes, dimensions)
        centroid_vec : np.ndarray of shape (dimensions,)
        sphere_radius : np.ndarray of shape (classes,)
        slab_radius : np.ndarray of shape (classes,)
        verbose : bool
            CVX verbose

        Returns
        -------
        c_opt :
            Optimal C value
        """
        self.cvx_y.value = y
        self.cvx_g.value = g.reshape(-1)
        self.cvx_theta.value = theta.reshape(-1)
        self.cvx_centroid.value = centroid.reshape(-1)
        self.cvx_centroid_vec.value = centroid_vec.reshape(-1)
        self.cvx_sphere_radius.value = sphere_radius
        self.cvx_slab_radius.value = slab_radius

        self.prob.solve(verbose=verbose)

        c_opt = self.cvx_c.value
        return c_opt


class Projector(object):
    """ Projector ???

    Solves the optimization problem:
    TODO
    """

    def __init__(self, use_sphere=True, use_slab=True):
        """ Projector ???

        Parameters
        ----------
        use_sphere
        use_slab
        """

        d = 3

        self.cvx_x = cvx.Variable(d)
        self.cvx_z = cvx.Parameter(d)
        self.cvx_centroid = cvx.Parameter(d)
        self.cvx_centroid_vec = cvx.Parameter(d)
        self.cvx_sphere_radius = cvx.Parameter(1)
        self.cvx_slab_radius = cvx.Parameter(1)

        self.cvx_x_c = self.cvx_x - self.cvx_centroid

        self.constraints = []
        if use_sphere:
            self.constraints.append(cvx.norm(self.cvx_x_c, 2) < self.cvx_sphere_radius)
        if use_slab:
            self.constraints.append(cvx.abs(cvx_dot(self.cvx_centroid_vec, self.cvx_x_c)) < self.cvx_slab_radius)

        self.objective = cvx.Minimize(cvx.norm(self.cvx_x - self.cvx_z, 2))        

        self.prob = cvx.Problem(self.objective, self.constraints)

    def project_onto_feasible_set(self, z, centroid, centroid_vec, sphere_radius, slab_radius,
                                   verbose=False):
        """ Project onto Feasible Set

        Parameters
        ----------
        z : ??
        centroid : np.ndarray of shape (classes, dimension)
        centroid_vec : np.ndarray of shape (dimensions,)
        sphere_radius : np.ndarray of shape (classes,)
        slab_radius : np.ndarray of shape (classes,)
        verbose : bool

        Returns
        -------
        x_proj :
            Data projected onto feasible set
        """

        P = get_projection_matrix(z, centroid, centroid_vec)
        
        self.cvx_z.value = P.dot(z.reshape(-1))
        self.cvx_centroid.value = P.dot(centroid.reshape(-1))
        self.cvx_centroid_vec.value = P.dot(centroid_vec.reshape(-1))
        self.cvx_sphere_radius.value = sphere_radius
        self.cvx_slab_radius.value = slab_radius

        self.prob.solve(verbose=verbose)

        x_opt = np.array(self.cvx_x.value).reshape(-1)
        
        return x_opt.dot(P)
