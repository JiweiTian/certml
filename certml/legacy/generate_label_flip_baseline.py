"""Generate Label Flip Baseline"""

import argparse
import numpy as np
import scipy.sparse as sparse
from certml import defenses
from certml.legacy import data_utils as data, datasets

##############
# Parameters #
##############
random_seed = 1

#########################
# Parse Input Arguments #
#########################

parser = argparse.ArgumentParser()
parser.add_argument('dataset_name', help='One of: imdb, enron, dogfish, mnist_17')
args = parser.parse_args()
dataset_name = args.dataset_name

assert dataset_name in ['imdb', 'enron', 'dogfish', 'mnist_17']

#################################################
# Load Dataset and Dataset Dependent Parameters #
#################################################
print('=== Dataset: %s ===' % dataset_name)
epsilons = datasets.DATASET_EPSILONS[dataset_name]
X_train, Y_train, X_test, Y_test = datasets.load_dataset(dataset_name)

# Extract Important Data Properties
class_map, centroids, centroid_vec, sphere_radii, slab_radii = data.get_data_params(
    X_train, Y_train, percentile=70)

# Calculate Distances from Centroids
sphere_dists_flip = defenses.compute_dists_under_Q(    
    X_train, -Y_train,
    Q=None,
    subtract_from_l2=False,
    centroids=centroids,
    class_map=class_map,    
    norm=2)    

slab_dists_flip = defenses.compute_dists_under_Q(    
    X_train, -Y_train,
    Q=centroid_vec,
    subtract_from_l2=False,
    centroids=centroids,
    class_map=class_map,    
    norm=2)

###################################################
# Determine Which Data is Within the Feasible Set #
###################################################

# We should only flip data within the feasible set
# as data outside will be removed by the defense and have no impact
feasible_flipped_mask = np.zeros(X_train.shape[0], dtype=bool)

for y in set(Y_train):
    class_idx_flip = class_map[-y]
    sphere_radius_flip = sphere_radii[class_idx_flip]
    slab_radius_flip = slab_radii[class_idx_flip]
    
    feasible_flipped_mask[Y_train == y] = (
        (sphere_dists_flip[Y_train == y] <= sphere_radius_flip) & 
        (slab_dists_flip[Y_train == y] <= slab_radius_flip))

print('Num positive points: %s' % np.sum(Y_train == 1))
print('Num negative points: %s' % np.sum(Y_train == -1))
print('Fraction of feasible positive points that can be flipped: %s' % np.mean(feasible_flipped_mask[Y_train == 1]))
print('Fraction of feasible negative points that can be flipped: %s' % np.mean(feasible_flipped_mask[Y_train == -1]))

##############################################
# Generate Poisoned Dataset for Each Epsilon #
##############################################
for epsilon in epsilons:
    if epsilon == 0:
        continue

    # Number of instances to flip according to epsilon
    num_copies = int(np.round(epsilon * X_train.shape[0]))

    # Randomly determine which instances to flip
    idx_to_copy = np.random.choice(
        np.where(feasible_flipped_mask)[0],
        size=num_copies,
        replace=True)

    # Flip labels of instances
    if sparse.issparse(X_train):
        X_modified = sparse.vstack((X_train, X_train[idx_to_copy, :]))
    else:
        X_modified = np.append(X_train, X_train[idx_to_copy, :], axis=0)
    Y_modified = np.append(Y_train, -Y_train[idx_to_copy])

    ################
    # Sanity Check #
    ################

    # Just to make sure nothing went wrong. Calculate the percentage
    # attack instances that are within the feasible set. This should be 100%.
    sphere_dists = defenses.compute_dists_under_Q(    
        X_modified, Y_modified,
        Q=None,
        subtract_from_l2=False,
        centroids=centroids,
        class_map=class_map,    
        norm=2)    
    slab_dists = defenses.compute_dists_under_Q(    
        X_modified, Y_modified,
        Q=centroid_vec,
        subtract_from_l2=False,
        centroids=centroids,
        class_map=class_map,    
        norm=2)    

    feasible_mask = np.zeros(X_modified.shape[0], dtype=bool)

    for y in set(Y_modified):
        class_idx = class_map[y]
        sphere_radius = sphere_radii[class_idx]
        slab_radius = slab_radii[class_idx]
        
        feasible_mask[Y_modified == y] = (
            (sphere_dists[Y_modified == y] <= sphere_radius) & 
            (slab_dists[Y_modified == y] <= slab_radius))

    print('Fraction of feasible points in attack: %s' % np.mean(feasible_mask[X_train.shape[0]:]))

    # Save Poisoned Dataset
    np.savez(
        datasets.get_labelflip_attack_npz_path(dataset_name, epsilon, norm_sq_constraint=None),
        poisoned_X_train=X_modified, 
        Y_train=Y_modified)
