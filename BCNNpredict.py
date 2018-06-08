#This file is the predicting part of the BCNN. The trained BCNN in BCNN.py predicts the class of images from a toy dataset.
# The image are divided in patches of 30*30 with a stride of 6.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow as tf
import scipy.io
import sklearn.model_selection as sk
import slidingWindows as sw

import LossFunction as lf
import selectPatch as sp
import predictionBCNN as pr

tf.logging.set_verbosity(tf.logging.DEBUG)


def cnn_model_fn(features, labels, mode, params):  
  """Model function for CNN."""
  # Input Layer
  # Reshape X to 4-D tensor: [batch_size*nbr_patch, width, height, channels]
  # ToyDataset are 30x30 pixels, and have one color channel  
  input_layer = tf.reshape(features["x"], [-1, 30, 30,1])
  input_layer=tf.cast(input_layer, tf.float32)
  # Convolutional Layer #1
  # Computes 10 features using a 5x5 filter with ReLU activation.
  # No padding.
  # Input Tensor Shape: [batch_size*nbr_patch, 30, 30, 1]
  # Output Tensor Shape: [batch_size*nbr_patch, 26, 26, 10]
  conv1 = tf.layers.conv2d(
      inputs=input_layer,
      filters=10,
      kernel_size=[5, 5],
      padding="valid",
      activation=tf.nn.relu)

  # Pooling Layer #1
  # First max pooling layer with a 2x2 filter and stride of 2
  # Input Tensor Shape: [batch_size*nbr_patch, 26, 26, 10]
  # Output Tensor Shape: [batch_size*nbr_patch, 13, 13, 10]
  pool1 = tf.layers.max_pooling2d(inputs=conv1, pool_size=[2, 2], strides=2)

  

  # Flatten tensor into a batch of vectors
  # Input Tensor Shape: [batch_size*nbr_patch, 13, 13, 10]
  # Output Tensor Shape: [batch_size*nbr_patch, 13 * 13 * 10]
  pool2_flat = tf.reshape(pool1, [-1, 13 * 13 * 10])
  

  # Dense Layer
  # Densely connected layer with 300 neurons
  # Input Tensor Shape: [batch_size*nbr_patch, 13 * 13 * 30]
  # Output Tensor Shape: [batch_size*nbr_patch, 300]
  dense = tf.layers.dense(inputs=pool2_flat, units=300, activation=tf.nn.relu)

  # Add dropout operation; 0.5 probability that element will be kept
  dropout = tf.layers.dropout(
      inputs=dense, rate=0.5, training=mode == tf.estimator.ModeKeys.TRAIN)

  # Logits layer
  # Input Tensor Shape: [batch_size*nbr_patch, 300]
  # Output Tensor Shape: [batch_size*nbr_patch, 2]
  logits = tf.layers.dense(inputs=dropout, units=3)

  predictions = {
      # Generate predictions (for PREDICT and EVAL mode)
      "classes": tf.argmax(input=logits, axis=1, name="class_pred"),
      # Add `softmax_tensor` to the graph. It is used for PREDICT and by the
      # `logging_hook`.
      "probabilities": tf.nn.softmax(logits, name="softmax_tensor")
  }
  if mode == tf.estimator.ModeKeys.PREDICT:
    return tf.estimator.EstimatorSpec(mode=mode, predictions=predictions)  
  
  
  # Calculate Loss (for both TRAIN and EVAL modes)
  selected_probabilities, size_current_batch = lf.selectionOfTheCorrectClassOnly(labels, predictions, params, mode) 
  selected_probabilities=tf.identity(selected_probabilities, name="correct_class")
  selected_probabilities= lf.spatialFactor(selected_probabilities, params)
  selected_probabilities=tf.identity(selected_probabilities, name="correct_class_withSF")
  loss, nbr_bag=lf.lossFunctionPCNN(params, mode, selected_probabilities, size_current_batch )
  
  
  # Configure the Training Op (for TRAIN mode)
  if mode == tf.estimator.ModeKeys.TRAIN:
    optimizer = tf.train.GradientDescentOptimizer(learning_rate=0.001)
    train_op = optimizer.minimize(
        loss=loss,
        global_step=tf.train.get_global_step())
    return tf.estimator.EstimatorSpec(mode=mode, loss=loss, train_op=train_op)

  # To come back from patch to one single value for one image
  #class_patch_max, which_patch_max=sp.findPatchOfMaxProbabilityBCNN (predictions, params, nbr_bag)
  #class_patch_max=tf.identity(class_patch_max, name="class_patch")
  totProb=pr.totalProbEachClass(predictions, params)
  totProb=tf.identity(totProb, name="totProb")
  class_patch_max=tf.argmax(totProb,1, name="majorityVote")
  
  
  label_image=sw.reduceLabelsToOnePerImage(labels, params)
  label_image=tf.identity(label_image, name="label_batch")
  
  #To show the most discriminative patch from the PREDICTED class
  elongated_MV=pr.elongatePredictedLabels(class_patch_max, params)
  pred_good_probabilities, size_current_batch = lf.selectionOfTheCorrectClassOnly(elongated_MV, predictions, params, mode)
  pred_good_probabilities= lf.spatialFactor(pred_good_probabilities, params)
  reshaped_prob=tf.reshape(pred_good_probabilities,[-1,params["nbr_patch"]])
  values, indices_pred =tf.nn.top_k(reshaped_prob,1)
  indices_pred=tf.identity(indices_pred, name="indices_pred")  

  
  #assert label_image.shape[0]==class_patch_max.shape[0], "Labels and data don't have the same size"
  #The inversion is done to compute the metrics for the second class
  inversed_label=tf.logical_not(tf.cast(label_image,tf.bool))
  inversed_label=tf.cast(inversed_label, tf.float32)
  inversed_pred=tf.logical_not(tf.cast(class_patch_max,tf.bool))
  inversed_pred=tf.cast(inversed_pred, tf.float32)

    # Add evaluation metrics (for EVAL mode)
  eval_metric_ops = {
      "accuracy": tf.metrics.accuracy(
          labels=label_image, predictions=class_patch_max),
      "TP":tf.metrics.true_positives(labels=label_image, predictions=class_patch_max),
      "FN":tf.metrics.false_negatives(labels=label_image, predictions=class_patch_max),
      "FP":tf.metrics.false_positives(labels=label_image, predictions=class_patch_max),
      "TP_class2":tf.metrics.true_positives(labels=inversed_label, predictions=inversed_pred),
      "FN_class2":tf.metrics.false_negatives(labels=inversed_label, predictions=inversed_pred),
      "FP_class2":tf.metrics.false_positives(labels=inversed_label, predictions=inversed_pred)
              }
  
  return tf.estimator.EstimatorSpec(
      mode=mode, loss=loss, eval_metric_ops=eval_metric_ops)




        
def main(unused_argv):
    #Load the data
    #class1 = scipy.io.loadmat('allClass1Para.mat')
    class1 = scipy.io.loadmat('allClass1Inversed.mat')
    class1=class1['allClass1']
    label1=np.ones(class1.shape[0])
    
    #class2 = scipy.io.loadmat('allClass2Para.mat')
    class2 = scipy.io.loadmat('allClass2Inversed.mat')
    class2=class2['allClass2']
    label0=np.zeros(class2.shape[0])
    
    data=np.concatenate((class2,class1), axis=0)
    label=np.concatenate((label0,label1), axis=0)
    
    #Divide it in train and test
    x_train, x_test, y_train, y_test = sk.train_test_split(data,label,test_size=0.10, random_state = 42)
    #x_train, x_test, y_train, y_test = sk.train_test_split(class2,label0,test_size=0.10, random_state = 42)
   
    stride=6
    size_patch=30
    all_patch_train, label_patch_train, nbr_patch=sw.sliding_window(x_train, y_train, stride, size_patch)
    all_patch_test, label_patch_test, nbr_patch=sw.sliding_window(x_test, y_test, stride, size_patch)
    
   
    
    #Show the first 
    #for i in range(3):
        
 #       sw.show_patches(i, x_test, all_patch_test,  nbr_patch)
 #       sw.show_one_image(i, x_test)
   
    
    # HYPER PARAMETERS
    #Size of the entire vector during training and evaluation
    batch_train=15*nbr_patch
    #batch_test=x_test.shape[0]*nbr_patch
    images_in_one_batch_test=15
    batch_test=images_in_one_batch_test*nbr_patch
    #In how many batches the test dataset can be divided? 
    #int(0.9) gives 0, which means that the the last batch will never go over the maximum of the test dataset
    how_many_batch_test=int(y_test.shape[0]/images_in_one_batch_test)
    print("how many batches in the test dataset ", how_many_batch_test)
    nbr_class=3
    #Number of the most discriminative patches that are going to be taken
    dMaxPatch=3
    #exec(open("save.py").read())
    
    
    
    # Create the Estimator
    mnist_classifier = tf.estimator.Estimator(
      model_fn=cnn_model_fn, model_dir="/tmp/BCNNtrain2_i", params= {"train":batch_train, "test":batch_test,
                                                                    "nbr_patch":nbr_patch, 
                                                                    "nbr_class":nbr_class,
                                                                    "size_patch":size_patch,
                                                                    "dMaxPatch":dMaxPatch,
                                                                    "images_in_one_batch_test":images_in_one_batch_test})

    # Set up logging for predictions
    # Log the values in the "Softmax" tensor with label "probabilities"
#    tensors_to_log = {"probabilities": "softmax_tensor"}
#    logging_hook = tf.train.LoggingTensorHook(
#    tensors=tensors_to_log, every_n_iter=1)
    
    #Train the model
#    train_input_fn = tf.estimator.inputs.numpy_input_fn(
#        x={"x": all_patch_train},
#        y=label_patch_train,
#        batch_size=batch_train,
#        num_epochs=None,
#        shuffle=False)
#    mnist_classifier.train(
#        input_fn=train_input_fn,
#        steps=200)
        #hooks=[logging_hook])
    
    #change here for evaluation with less batches
    how_many_batch_test=5
    
    TPs_1   =np.zeros([how_many_batch_test])
    FPs_1   =np.zeros([how_many_batch_test])
    FNs_1   =np.zeros([how_many_batch_test])
    TPs_2   =np.zeros([how_many_batch_test])
    FPs_2   =np.zeros([how_many_batch_test])
    FNs_2   =np.zeros([how_many_batch_test])
   
    #for i in range(how_many_batch_test):
    for i in range(how_many_batch_test):
        
        #Set up logging for predictions
        #Log the values in the "Softmax" tensor with label "probabilities"
        tensors_to_log = {"indices_pred":"indices_pred"}#"Predictions":"softmax_tensor","classes_pred":"class_pred",
#                          "totProb":"totProb","true_label": "label_batch","prediction": "majorityVote" }
        logging_hook = tf.train.LoggingTensorHook(
            tensors=tensors_to_log, every_n_iter=1)
        
        # Evaluate the model and print results
        #Example with a dataset of 600, batch size of 200
        #First: 0  =>199
        #Second 200=>399
        #Third  400=>599
        eval_input_fn = tf.estimator.inputs.numpy_input_fn(
          x={"x": all_patch_test[batch_test*i:(batch_test*(i+1))]},
          y=label_patch_test[batch_test*i:(batch_test*(i+1))],
          #x={"x": all_patch_test},
          #y=label_patch_test,
          batch_size=batch_test,
          num_epochs=1,
          shuffle=False)
        eval_results = mnist_classifier.evaluate(input_fn=eval_input_fn, hooks=[logging_hook])
        
    
    
        TPs_1[i]   =eval_results["TP"]
        FPs_1[i]   =eval_results["FP"]
        FNs_1[i]   =eval_results["FN"]
        TPs_2[i]   =eval_results["TP_class2"]
        FPs_2[i]   =eval_results["FP_class2"]
        FNs_2[i]   =eval_results["FN_class2"]
          
        
    TP_1   =np.sum(TPs_1)
    FP_1   =np.sum(FPs_1)
    FN_1   =np.sum(FNs_1)
    TP_2   =np.sum(TPs_2)
    FP_2   =np.sum(FPs_2)
    FN_2   =np.sum(FNs_2)
    
    print("First Class")     
    recall_1=TP_1/(TP_1+FN_1)
    precision_1=TP_1/(TP_1+FP_1)
    F1_1=2*(precision_1*recall_1)/(precision_1+recall_1)
    
    print("recall    ", recall_1)
    #How many relevant items are selected
    print("precision ", precision_1)
    #Combination of the two above
    print("F1        ", F1_1)
    

    print("Second Class")  
    
    recall_2=TP_2/(TP_2+FN_2)
    precision_2=TP_2/(TP_2+FP_2)
    F1_2=2*(precision_2*recall_2)/(precision_2+recall_2)

    print("recall    ", recall_2)
    #How many relevant items are selected
    print("precision ", precision_2)
    #Combination of the two above
    print("F1        ", F1_2)    
    
    print("Total")
    F1=(F1_1+F1_2)/2
    print("F1_tot    ", F1)   

if __name__ == "__main__":
    tf.app.run()
