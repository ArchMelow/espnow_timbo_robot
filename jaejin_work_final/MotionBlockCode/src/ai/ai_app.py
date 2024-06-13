# Run simple AI applications

import microlite
import io
import os

# constants
MAX_MODEL_CAPACITY_IN_BYTES = 2488
counter = 1
kXrange = 2.0 * 3.14159265359
steps = 1000

MLP_current_input = None


# The input passed to the pretrained MLP (You can create one in Edge Impulse.)
def model_input_cb(microlite_interpreter):
    
    global MLP_current_input
    
    # convert input to a tensorflow tensor
    inputTensor = microlite_interpreter.getInputTensor(0)
    
    # compute input to the MLP
    position = counter*1.0
    x = position * kXrange/steps
    MLP_current_input = x

    # quantize the input tensor to int8
    x_quantized = inputTensor.quantizeFloatToInt8(x)

    inputTensor.setValue(0, x_quantized)

# The output of the pretrained MLP.
# you can see the result in Thonny Plotter
def model_output_cb(microlite_interpreter):
    global MLP_current_input
    
    outputTensor = microlite_interpreter.getOutputTensor(0)
    y_quantized = outputTensor.getValue(0)
    y = outputTensor.quantizeInt8ToFloat(y_quantized)

    print ("%f,%f" % (MLP_current_input,y))


# running simple "Hello World" application from https://github.com/ArchMelow/micropython_tflite/tree/main/examples/hello-world
# modify this function for your own project.
# This function is only for loading/running MLPs. Modify it for your own needs.

def AI_app(runner_obj):
    # search ./model folder.
    
    global counter
    
    model_list = list(os.listdir('./model'))
    
    # ./model folder can only contain only one file, for now.
    if len(model_list) != 1:
        print('./model folder can only contain only one file, for now.')
        return
    
    model_file_ = './model/' + str(model_list[0])
    
    # model has to be of format .tflite.
    if model_file_.split('/')[-1].split('.')[-1] != 'tflite':
        print('invalid model file format.')
        return
    
    try:
        model = bytearray(MAX_MODEL_CAPACITY_IN_BYTES)
        model_file = io.open(model_file_, 'rb')
        print(f'Successfully loaded model {model_file_}.')
        model_file.readinto(model)
        model_file.close()
    except Exception as E:
        print(f'Exception occurred when loading the model : {E}')
    
    interp = microlite.interpreter(model, 2048, model_input_cb, model_output_cb)
    
    # run with simple inputs (inputs and outputs are processed in callback functions given in the above function)
    
    print ("x, y")
    for c in range(steps):
        interp.invoke()
        counter = counter + 1
    
    
    
