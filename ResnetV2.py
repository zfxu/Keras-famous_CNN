import keras
from keras.layers import Conv2D, MaxPooling2D, AveragePooling2D
from keras.layers import Dense, BatchNormalization, Activation
from keras.layers import Flatten, Input
from keras.layers.merge import  add
from keras.regularizers import  l2
from keras import backend as K
from keras.models import Model
import numpy as np



class resnetv2_builder:

    def __init__(self, input_shape, output_units, block_fn = "bottleneck", num_blocks = [3,4,6,3], num_filters = [64,128,256,512],
                 init_kernel = (7,7), init_strides = (2,2), init_filters = 64, init_maxpooling = True,
                 regularizer = l2(1e-4), initializer = "he_normal"):

        '''
        constructor of resnetv2_builder

        :param input_shape: input shape of dataset
        :param output_units: classification labels
        :param block_fn: type of block function you want to use, if the Convolution layer < 50 -> basic, bottlenect for layer > 50
        :param num_blocks: number of block in each stages
        :param num_filters: number of filters in each stages
        :param init_kernel: The kernel size for first convolution layer
        :param init_strides: The stride size for first convolution layer
        :param init_filters: The number of filter for first convolution layer
        :param init_maxpooling: Use the maxpooling after first convolution or not
        :param regularizer: regularizer for convolution layer
        :param initializer: initializer for convolution and fully-connect layer

        '''
        assert len(input_shape) == 3, "input shape should has dim 3 ( row, col, channel or channel, row, col )"
        assert block_fn == "bottleneck" or block_fn == "basic", "wrong block function, should be bottleneck or basic"
        assert len(num_blocks) == len(num_filters), "num_blocks should has same length as num_filters"
        assert len(num_blocks) == len(num_filters), "The length of num_blocks should equal to the length of num_filters"


        self.input_shape = input_shape
        self.output_units = output_units
        self.block_fn = block_fn
        self.num_blocks = np.asarray(num_blocks, dtype = int)
        self.num_filters = np.asarray(num_filters, dtype = int)
        self.init_kernel = init_kernel
        self.init_strides = init_strides
        self.init_filters = init_filters
        self.init_maxpooling = init_maxpooling
        self.regularizer = regularizer
        self.initializer = initializer

        if K.image_dim_ordering() == "tf":
            self.row_axis = 1
            self.col_axis = 2
            self.channel_axis = 3
        else:
            self.row_axis = 2
            self.col_axis = 3
            self.channel_axis = 1

    def _cn_bn_relu(self, filters = 64, kernel_size = (3,3), strides = (1,1), padding = "same",
                    kernel_regularizer = l2(1e-4), kernel_initializer = "he_normal"):
        '''
        convenient function to build convolution -> batch_nromalization -> relu activation layers
        '''

        def f(input_x):

            x = Conv2D(filters = filters, kernel_size = kernel_size, strides = strides, padding = padding,
                             kernel_regularizer = kernel_regularizer, kernel_initializer = kernel_initializer)(input_x)
            x = BatchNormalization(axis = self.channel_axis)(x)
            x = Activation("relu")(x)

            return x

        return f

    def _bn_relu_cn(self, filters = 64, kernel_size = (3,3), strides = (1,1), padding = "same",
                    kernel_regularizer = l2(1e-4), kernel_initializer = "he_normal"):
        '''
        convenient function to build batch_nromalization -> relu activation -> convolution layers
        '''
        def f(input_x):

            x = BatchNormalization(axis = self.channel_axis)(input_x)
            x = Activation("relu")(x)
            x = Conv2D(filters = filters, kernel_size = kernel_size, strides = strides, padding = padding,
                       kernel_regularizer = kernel_regularizer, kernel_initializer = kernel_initializer)(x)

            return x

        return f

    def _shortcut(self, input_x, residual):

        '''
        Member function for merging input and residual layers
        '''

        input_dim = K.int_shape(input_x)
        res_dim = K.int_shape(residual)

        stride_width = int(round(input_dim[self.col_axis] / res_dim[self.col_axis]))
        stride_height = int(round(input_dim[self.row_axis] / res_dim[self.row_axis]))

        x = input_x

        if stride_height != 1 or stride_width != 1 or input_dim[self.channel_axis] != res_dim[self.channel_axis]:

            x = Conv2D(filters = res_dim[self.channel_axis], kernel_size = (1,1), strides = (stride_width, stride_height),
                       padding = "same", kernel_regularizer = self.regularizer, kernel_initializer = self.initializer)(x)

        return add([x,residual])


    def basic_block(self, filters, strides = (1,1), first_block_in_first_stage = False):
        '''
        In paper, the basic block only be used when the layers you want is smaller than 50
        function to build bottleneck block, which compose by 2 batch normalization -> relu -> convolution blocks
        :param first_block_in_first_stage: the flag of whether current block is at first block and first stage
        :return: return a basic block
        '''
        def f(input_x):

            x = input_x
            if first_block_in_first_stage:
                #when the current layer is in first block of first stage
                #we only do convolution since we just did the MaxPooling, Batch Normalization and activation
                x = Conv2D(filters = filters, kernel_size = (3,3), strides = (1,1), padding = "same",
                           kernel_regularizer = self.regularizer, kernel_initializer = self.initializer)(x)

            else:

                x = self._bn_relu_cn(filters = filters, kernel_size = (3,3), strides = strides,
                                kernel_initializer = self.initializer, kernel_regularizer = self.regularizer)(x)

            x = self._bn_relu_cn(filters = filters, kernel_size = (3,3), strides = (1,1),
                            kernel_initializer = self.initializer, kernel_regularizer = self.regularizer)(x)

            return self._shortcut(input_x = input_x, residual = x)

        return f

    def bottleneck_block(self, filters, strides = (1,1), first_block_in_first_stage = False):
        '''
        In paper, the bottleneck block only be used when the layers you want is bigger than 49
        function to build bottleneck block, which compose by 3 batch normalization -> relu -> convolution blocks
        :param first_block_in_first_stage: the flag of whether current block is at first block and first stage
        :return: return a bottleneck block
        '''
        def f(input_x):

            x = input_x

            if first_block_in_first_stage:
                # when the current layer is in first block of first stage
                # we only do convolution since we just did the MaxPooling, Batch Normalization and activation
                x = Conv2D(filters = filters, kernel_size = (1,1), strides = (1,1), padding = "same",
                           kernel_regularizer = self.regularizer, kernel_initializer = self.initializer)(x)
            else:

                x = self._bn_relu_cn(filters = filters, kernel_size = (1,1), strides = strides, padding = "same",
                                kernel_regularizer = self.regularizer, kernel_initializer = self.initializer)(x)

            x = self._bn_relu_cn(filters = filters, kernel_size = (3,3), strides = (1,1),
                            kernel_regularizer = self.regularizer, kernel_initializer = self.initializer)(x)

            x = self._bn_relu_cn(filters = filters * 4, kernel_size = (1,1), strides = (1,1),
                            kernel_regularizer = self.regularizer, kernel_initializer = self.initializer)(x)

            return self._shortcut(input_x = input_x, residual = x)

        return f

    def _resnet_block(self, filters, blocks, is_first_stage = False):
        '''
        :param filters: filter number of current stage
        :param blocks: block number of current stage
        :param is_first_stage: flag of whether current stage is first stage or not
        :return: A resnet block which build by several basic or bottleneck blocks
        '''
        def f(input_x):

            x = input_x

            for block in range(blocks):
                strides = (1,1)
                if is_first_stage != True and block == 0:
                    strides = (2,2)

                if self.block_fn == "basic":
                    x = self.basic_block(filters = filters, strides = strides, first_block_in_first_stage = is_first_stage and (block == 0))(x)
                else:
                    x = self.bottleneck_block(filters = filters, strides = strides, first_block_in_first_stage = is_first_stage and (block == 0))(x)

            return x

        return f


    def build_resnet(self):
        '''
        The main function to build a model
        :return: Return a resnet v2 model
        '''
        input_x = Input(self.input_shape)

        x = self._cn_bn_relu(filters = self.init_filters, kernel_size = self.init_kernel, strides = self.init_strides,
                   padding = "same", kernel_regularizer = self.regularizer, kernel_initializer = self.initializer)(input_x)

        if self.init_maxpooling:
            x = MaxPooling2D(pool_size = (3,3), strides = (2,2), padding = "same")(x)

        for i,(blocks, filters) in  enumerate(zip(self.num_blocks, self.num_filters)):
            x = self._resnet_block(filters = filters, blocks = blocks, is_first_stage = (i==0))(x)

        x = BatchNormalization(axis = self.channel_axis)(x)
        x = Activation("relu")(x)

        final_shape = K.int_shape(x)

        x = AveragePooling2D(pool_size = (final_shape[self.row_axis], final_shape[self.col_axis]), strides = (1,1))(x)
        x = Flatten()(x)

        output_x = Dense(units = self.output_units, kernel_initializer = self.initializer, activation = "softmax")(x)

        res_model = Model(inputs = [input_x], outputs = [output_x])
        return res_model





