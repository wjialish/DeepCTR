from tensorflow.python.keras.layers import Layer,Dense,Activation,Dropout,BatchNormalization,concatenate
from tensorflow.python.keras.regularizers import  l2
from tensorflow.python.keras.initializers import  RandomNormal,Zeros,glorot_normal,glorot_uniform
from tensorflow.python.keras import backend as K
from tensorflow.python.keras.activations import  softmax
from .activations import  Dice
import tensorflow as tf


class FM(Layer):
    """Factorization Machine models pairwise (order-2) feature interactions without linear term and bias.

      Input shape
        - 3D tensor with shape: ``(batch_size,field_size,embedding_size)``.

      Output shape
        - 2D tensor with shape: ``(batch_size, 1)``.
        
      References
        - [Factorization Machines](https://www.csie.ntu.edu.tw/~b97053/paper/Rendle2010FM.pdf)
    """
    def __init__(self, **kwargs):

        super(FM, self).__init__(**kwargs)

    def build(self, input_shape):
        if len(input_shape) !=3 :
            raise ValueError("Unexpected inputs dimensions %d, expect to be 3 dimensions"% (len(input_shape)))

        super(FM, self).build(input_shape)  # Be sure to call this somewhere!

    def call(self, inputs,**kwargs):

        if K.ndim(inputs) !=3 :
            raise ValueError("Unexpected inputs dimensions %d, expect to be 3 dimensions"% (K.ndim(inputs)))

        concated_embeds_value = inputs

        square_of_sum =  K.square(K.sum(concated_embeds_value, axis=1, keepdims=True))
        sum_of_square = K.sum(concated_embeds_value * concated_embeds_value, axis=1, keepdims=True)
        cross_term = square_of_sum - sum_of_square
        cross_term = 0.5 * K.sum(cross_term, axis=2, keepdims=False)

        return cross_term
    
    def compute_output_shape(self, input_shape):
        return (None, 1)


class AFMLayer(Layer):
    """Attentonal Factorization Machine models pairwise (order-2) feature interactions without linear term and bias.

      Input shape
        - A list of 3D tensor with shape: ``(batch_size,1,embedding_size)``.

      Output shape
        - 2D tensor with shape: ``(batch_size, 1)``.

      Arguments
      
        - **attention_factor** : Positive integer, dimensionality of the attention network output space.

        - **l2_reg_w** : float between 0 and 1. L2 regularizer strength applied to attention network.

        - **keep_prob** : float between 0 and 1. Fraction of the attention net output units to keep. 

        - **seed** : A Python integer to use as random seed.

      References
        - [Attentional Factorization Machines : Learning the Weight of Feature Interactions via Attention Networks](https://arxiv.org/pdf/1708.04617.pdf)
    """

    def __init__(self, attention_factor=4, l2_reg_w=0,keep_prob=1.0,seed=1024, **kwargs):
        self.attention_factor = attention_factor
        self.l2_reg_w = l2_reg_w
        self.keep_prob = keep_prob
        self.seed = seed
        super(AFMLayer, self).__init__(**kwargs)

    def build(self, input_shape):

        if not isinstance(input_shape, list) or len(input_shape) < 2:
            raise ValueError('A `AttentionalFM` layer should be called '
                             'on a list of at least 2 inputs')

        shape_set = set()
        reduced_input_shape = [shape.as_list() for shape in input_shape]
        for i in range(len(input_shape)):
            shape_set.add(tuple(reduced_input_shape[i]))

        if len(shape_set) > 1:
            raise ValueError('A `AttentionalFM` layer requires '
                             'inputs with same shapes '
                             'Got different shapes: %s' % (shape_set))

        if len(input_shape[0]) != 3 or input_shape[0][1] != 1:
            raise ValueError('A `AttentionalFM` layer requires '
                             'inputs of a list with same shape tensor like (None,1,embedding_size)'
                             'Got different shapes: %s' % (input_shape[0]))



        embedding_size = input_shape[0][-1]

        #self.attention_W = self.add_weight(shape=(embedding_size, self.attention_factor), initializer=glorot_normal(seed=self.seed),
        #                                   name="attention_W")
        #self.attention_b = self.add_weight(shape=(self.attention_factor,), initializer=Zeros(), name="attention_b")
        self.projection_h = self.add_weight(shape=(self.attention_factor, 1), initializer=glorot_normal(seed=self.seed),
                                            name="projection_h")
        self.projection_p = self.add_weight(shape=(embedding_size, 1), initializer=glorot_normal(seed=self.seed), name="projection_p")
        super(AFMLayer, self).build(input_shape)  # Be sure to call this somewhere!

    def call(self, inputs,**kwargs):

        if K.ndim(inputs[0]) != 3:
            raise ValueError("Unexpected inputs dimensions %d, expect to be 3 dimensions" % (K.ndim(inputs)))

        embeds_vec_list = inputs
        row = []
        col = []
        num_inputs = len(embeds_vec_list)
        for i in range(num_inputs - 1):
            for j in range(i + 1, num_inputs):
                row.append(i)
                col.append(j)
        p = concatenate([embeds_vec_list[idx] for idx in row],axis=1)# batch num_pairs k
        q = concatenate([embeds_vec_list[idx] for idx in col],axis=1)  # Reshape([num_pairs, self.embedding_size])
        inner_product = p * q

        bi_interaction = inner_product

        attention_temp = Dense(self.attention_factor,'relu',kernel_regularizer=l2(self.l2_reg_w))(bi_interaction)
        attention_weight = softmax(K.dot(attention_temp, self.projection_h),axis=1)

        attention_output = K.sum(attention_weight*bi_interaction,axis=1)
        attention_output = tf.nn.dropout(attention_output,self.keep_prob,seed=1024)
            # Dropout(1-self.keep_prob)(attention_output)
        afm_out = K.dot(attention_output, self.projection_p)

        return afm_out

    def compute_output_shape(self, input_shape):

        if not isinstance(input_shape, list):
            raise ValueError('A `AFMLayer` layer should be called '
                             'on a list of inputs.')
        return (None, 1)

    def get_config(self,):
        config = {'attention_factor': self.attention_factor,'l2_reg_w':self.l2_reg_w, 'keep_prob':self.keep_prob, 'seed':self.seed}
        base_config = super(AFMLayer, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class PredictionLayer(Layer):

    
    def __init__(self, activation='sigmoid',use_bias=True, **kwargs):
        self.activation = activation
        self.use_bias = use_bias
        super(PredictionLayer, self).__init__(**kwargs)

    def build(self, input_shape):

        if self.use_bias:
            self.global_bias = self.add_weight(shape=(1,), initializer=Zeros(),name="global_bias")

        super(PredictionLayer, self).build(input_shape)  # Be sure to call this somewhere!

    def call(self, inputs,**kwargs):
        x = inputs
        if self.use_bias:
            x = K.bias_add(x, self.global_bias, data_format='channels_last')
        if isinstance(self.activation,str):
            output = Activation(self.activation)(x)
        else:
            output = self.activation(x)

        output = K.reshape(output,(-1,1))

        return output

    def compute_output_shape(self, input_shape):
        return (None,1)

    def get_config(self,):
        config = {'activation': self.activation,'use_bias':self.use_bias}
        base_config = super(PredictionLayer, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

class CrossNet(Layer):
    """The Cross Network part of Deep&Cross Network model,which leans both low and high degree cross feature.

      Input shape
        - 2D tensor with shape: ``(batch_size, units)``.

      Output shape
        - 2D tensor with shape: ``(batch_size, units)``.

      Arguments
        - **layer_num**: Positive integer, the cross layer number

        - **l2_reg**: float between 0 and 1. L2 regularizer strength applied to the kernel weights matrix

        - **seed**: A Python integer to use as random seed.

      References
        - [Deep & Cross Network for Ad Click Predictions](https://arxiv.org/abs/1708.05123)
    """
    def __init__(self, layer_num=1,l2_reg=0,seed=1024, **kwargs):
        self.layer_num = layer_num
        self.l2_reg = l2_reg
        self.seed = seed
        super(CrossNet, self).__init__(**kwargs)

    def build(self, input_shape):

        if len(input_shape) != 2:
            raise ValueError("Unexpected inputs dimensions %d, expect to be 2 dimensions" % (len(input_shape),))

        dim = input_shape[-1]
        self.kernels = [self.add_weight(name='kernel'+str(i),
                                        shape=(dim, 1),
                                       initializer=glorot_normal(seed=self.seed),
                                        regularizer=l2(self.l2_reg),
                                        trainable=True) for i in range(self.layer_num)]
        self.bias = [self.add_weight(name='bias'+str(i) ,
                                     shape=(dim,1),
                                    initializer=Zeros(),
                                     trainable=True) for i in range(self.layer_num)]
        super(CrossNet, self).build(input_shape)  # Be sure to call this somewhere!

    def call(self, inputs,**kwargs):
        if K.ndim(inputs) !=2 :
            raise ValueError("Unexpected inputs dimensions %d, expect to be 2 dimensions"% (K.ndim(inputs)))

        x = inputs
        dim = x.get_shape()[-1]
        x_0 = K.reshape(x,[-1,dim, 1])
        x_l = x_0
        for i in range(self.layer_num):
            dot_ = tf.matmul(x_0, tf.transpose(x_l, [0, 2, 1]))  # K.dot(x_0,K.transpose(x_l))
            dot_ = K.dot(dot_, self.kernels[i])
            #x_l = K.bias_add(dot_+ x_l,self.bias[i]) # K.bias_add(dot_, self.bias)
            x_l = dot_ + x_l + self.bias[i]#K.reshape(self.bias[i],[1,dim,1])
        x_l = K.reshape(x_l, [-1, dim])
        return x_l

    def get_config(self,):

        config = {'layer_num': self.layer_num,'l2_reg':self.l2_reg,'seed':self.seed}
        base_config = super(CrossNet, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class MLP(Layer):
    """The Multi Layer Percetron
        
      Input shape
        - nD tensor with shape: ``(batch_size, ..., input_dim)``. The most common situation would be a 2D input with shape ``(batch_size, input_dim)``.

      Output shape
        - nD tensor with shape: ``(batch_size, ..., hidden_size[-1])``. For instance, for a 2D input with shape `(batch_size, input_dim)`, the output would have shape ``(batch_size, hidden_size[-1])``.

      Arguments
        - **hidden_size**:list of positive integer, the layer number and units in each layer.

        - **activation**: Activation function to use.

        - **l2_reg**: float between 0 and 1. L2 regularizer strength applied to the kernel weights matrix.

        - **keep_prob**: float between 0 and 1. Fraction of the units to keep. 

        - **use_bn**: bool. Whether use BatchNormalization before activation or not.

        - **seed**: A Python integer to use as random seed.
    """

    def __init__(self,  hidden_size, activation,l2_reg, keep_prob, use_bn,seed,**kwargs):
        self.hidden_size = hidden_size
        self.activation =activation
        self.keep_prob = keep_prob
        self.seed = seed
        self.l2_reg = l2_reg
        self.use_bn = use_bn
        super(MLP, self).__init__(**kwargs)

    def build(self, input_shape):

        super(MLP, self).build(input_shape)  # Be sure to call this somewhere!

    def call(self, inputs,**kwargs):
        deep_input = inputs
        deep_input = Dropout(1 - self.keep_prob)(deep_input)

        for l in range(len(self.hidden_size)):
            fc = Dense(self.hidden_size[l], activation=None, \
                       kernel_initializer=glorot_normal(seed=self.seed), \
                       kernel_regularizer=l2(self.l2_reg))(deep_input)
            if self.use_bn:
                fc = BatchNormalization()(fc)

            if isinstance(self.activation,str):
                fc = Activation(self.activation)(fc)
            else:
                fc = self.activation(fc,name=self.name+"act"+str(l))

            fc = Dropout(1 - self.keep_prob)(fc)

            deep_input = fc

        return deep_input
    def compute_output_shape(self, input_shape):
        if len(self.hidden_size) > 0:
            shape = input_shape[:-1] + (self.hidden_size[-1],)
        else:
            shape = input_shape

        return tuple(shape)

    def get_config(self,):
        config = {'activation': self.activation,'hidden_size':self.hidden_size, 'l2_reg':self.l2_reg,'use_bn':self.use_bn, 'keep_prob':self.keep_prob,'seed': self.seed}
        base_config = super(MLP, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

class BiInteractionPooling(Layer):
    """Bi-Interaction Layer used in Neural FM,compress the pairwise element-wise product of features into one single vector.

      Input shape
        - A list of 3D tensor with shape:``(batch_size,field_size,embedding_size)``.

      Output shape
        - 2D tensor with shape: ``(batch_size, embedding_size)``.

      References
        - [Neural Factorization Machines for Sparse Predictive Analytics](http://arxiv.org/abs/1708.05027)
    """

    def __init__(self, **kwargs):

        super(BiInteractionPooling, self).__init__(**kwargs)

    def build(self, input_shape):

        if len(input_shape) != 3 :
            raise ValueError("Unexpected inputs dimensions %d, expect to be 3 dimensions"% (len(input_shape)))

        super(BiInteractionPooling, self).build(input_shape)  # Be sure to call this somewhere!

    def call(self, inputs,**kwargs):

        if K.ndim(inputs) !=3 :
            raise ValueError("Unexpected inputs dimensions %d, expect to be 3 dimensions"% (K.ndim(inputs)))

        concated_embeds_value = inputs
        square_of_sum =  K.square(K.sum(concated_embeds_value, axis=1, keepdims=True))
        sum_of_square = K.sum(concated_embeds_value * concated_embeds_value, axis=1, keepdims=True)
        cross_term = 0.5*(square_of_sum - sum_of_square)
        cross_term = K.reshape(cross_term,(-1,inputs.get_shape()[-1]))
        return cross_term

    def compute_output_shape(self, input_shape):
        return (None, input_shape[-1])

class OutterProductLayer(Layer):
    """OutterProduct Layer used in PNN.This implemention  is adapted from code that the author of the paper published on https://github.com/Atomu2014/product-nets.

      Input shape
            - A list of N 3D tensor with shape: ``(batch_size,1,embedding_size)``.

      Output shape
            - 2D tensor with shape:``(batch_size, N*(N-1)/2 )``.
    
      Arguments
            - **kernel_type**: str. The kernel weight matrix type to use,can be mat,vec or num

            - **seed**: A Python integer to use as random seed.

      References
            - [Product-based Neural Networks for User Response Prediction](https://arxiv.org/pdf/1611.00144.pdf)
    """

    def __init__(self, kernel_type='mat', seed=1024, **kwargs):
        if kernel_type not in ['mat', 'vec', 'num']:
            raise ValueError("kernel_type must be mat,vec or num")
        self.kernel_type = kernel_type
        self.seed = seed
        super(OutterProductLayer, self).__init__(**kwargs)

    def build(self, input_shape):

        if not isinstance(input_shape, list) or len(input_shape) < 2:
            raise ValueError('A `OutterProductLayer` layer should be called '
                             'on a list of at least 2 inputs')

        reduced_inputs_shapes = [shape.as_list() for shape in input_shape]
        shape_set = set()

        for i in range(len(input_shape)):
            shape_set.add(tuple(reduced_inputs_shapes[i]))

        if len(shape_set) > 1:
            raise ValueError('A `OutterProductLayer` layer requires '
                             'inputs with same shapes '
                             'Got different shapes: %s' % (shape_set))

        if  len(input_shape[0]) != 3 or input_shape[0][1] != 1:
            raise ValueError('A `OutterProductLayer` layer requires '
                             'inputs of a list with same shape tensor like (None,1,embedding_size)'
                             'Got different shapes: %s' % (input_shape[0]))
        num_inputs = len(input_shape)
        num_pairs = int(num_inputs * (num_inputs - 1) / 2)
        input_shape = input_shape[0]
        embed_size = input_shape[-1]
        if self.kernel_type == 'mat':

            self.kernel = self.add_weight(shape=(embed_size,num_pairs,embed_size), initializer=glorot_uniform(seed=self.seed),
                                      name='kernel')
        elif self.kernel_type == 'vec':
            self.kernel = self.add_weight(shape=(num_pairs,embed_size,),initializer=glorot_uniform(self.seed),name='kernel'
                                          )
        elif self.kernel_type == 'num':
            self.kernel = self.add_weight(shape=(num_pairs,1),initializer=glorot_uniform(self.seed),name='kernel')

        super(OutterProductLayer, self).build(input_shape)  # Be sure to call this somewhere!

    def call(self, inputs,**kwargs):

        if K.ndim(inputs[0]) != 3:
            raise ValueError("Unexpected inputs dimensions %d, expect to be 3 dimensions" % (K.ndim(inputs)))

        embed_list = inputs
        row = []
        col = []
        num_inputs = len(embed_list)
        for i in range(num_inputs - 1):
            for j in range(i + 1, num_inputs):
                row.append(i)
                col.append(j)
        p = K.concatenate([embed_list[idx] for idx in row],axis=1)  # batch num_pairs k
        q = K.concatenate([embed_list[idx] for idx in col],axis=1)  # Reshape([num_pairs, self.embedding_size])

        #-------------------------
        if self.kernel_type == 'mat':
            p = tf.expand_dims(p, 1)
            # k     k* pair* k
            # batch * pair
            kp = tf.reduce_sum(

                # batch * pair * k

                tf.multiply(

                    # batch * pair * k

                    tf.transpose(

                        # batch * k * pair

                        tf.reduce_sum(

                            # batch * k * pair * k

                            tf.multiply(

                                p, self.kernel),

                            -1),

                        [0, 2, 1]),

                    q),

                -1)
        else:
            # 1 * pair * (k or 1)

            k = tf.expand_dims(self.kernel, 0)

            # batch * pair

            kp = tf.reduce_sum(p * q * k, -1)

            # p q # b * p * k

        return kp

    def compute_output_shape(self, input_shape):
        num_inputs = len(input_shape)
        num_pairs = int(num_inputs * (num_inputs - 1) / 2)
        return (None, num_pairs)

    def get_config(self,):
        config = {'kernel_type': self.kernel_type,'seed': self.seed}
        base_config = super(OutterProductLayer, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

class InnerProductLayer(Layer):
    """InnerProduct Layer used in PNN that compute the element-wise product or inner product between feature vectors.

      Input shape
        - A list of N 3D tensor with shape: ``(batch_size,1,embedding_size)``.

      Output shape
        - 2D tensor with shape: ``(batch_size, N*(N-1)/2 )`` if use reduce_sum. or 3D tensor with shape: ``(batch_size, N*(N-1)/2, embedding_size )`` if not use reduce_sum.

      Arguments
        - **reduce_sum**: bool. Whether return inner product or element-wise product

      References
            - [Product-based Neural Networks for User Response Prediction](https://arxiv.org/pdf/1611.00144.pdf)
    """

    def __init__(self,reduce_sum=True,**kwargs):
        self.reduce_sum = reduce_sum
        super(InnerProductLayer, self).__init__(**kwargs)

    def build(self, input_shape):

        if not isinstance(input_shape, list) or len(input_shape) < 2:
            raise ValueError('A `InnerProductLayer` layer should be called '
                             'on a list of at least 2 inputs')

        reduced_inputs_shapes = [shape.as_list() for shape in input_shape]
        shape_set = set()

        for i in range(len(input_shape)):
            shape_set.add(tuple(reduced_inputs_shapes[i]))

        if len(shape_set) > 1:
            raise ValueError('A `InnerProductLayer` layer requires '
                             'inputs with same shapes '
                             'Got different shapes: %s' % (shape_set))

        if len(input_shape[0]) != 3 or input_shape[0][1] != 1:
            raise ValueError('A `InnerProductLayer` layer requires '
                             'inputs of a list with same shape tensor like (None,1,embedding_size)'
                             'Got different shapes: %s' % (input_shape[0]))
        super(InnerProductLayer, self).build(input_shape)  # Be sure to call this somewhere!

    def call(self, inputs,**kwargs):
        if K.ndim(inputs[0]) != 3:
            raise ValueError("Unexpected inputs dimensions %d, expect to be 3 dimensions" % (K.ndim(inputs)))

        embed_list = inputs
        row = []
        col = []
        num_inputs = len(embed_list)
        num_pairs = int(num_inputs * (num_inputs - 1) / 2)


        for i in range(num_inputs - 1):
            for j in range(i + 1, num_inputs):
                row.append(i)
                col.append(j)
        p = K.concatenate([embed_list[idx] for idx in row],axis=1)# batch num_pairs k
        q = K.concatenate([embed_list[idx] for idx in col],axis=1)  # Reshape([num_pairs, self.embedding_size])
        inner_product = p * q
        if self.reduce_sum:
            inner_product = K.sum(inner_product, axis=2, keepdims=False)
        return inner_product


    def compute_output_shape(self, input_shape):
        num_inputs = len(input_shape)
        num_pairs = int(num_inputs * (num_inputs - 1) / 2)
        input_shape = input_shape[0]
        embed_size = input_shape[-1]
        if self.reduce_sum:
            return (input_shape[0],num_pairs)
        else:
            return (input_shape[0],num_pairs,embed_size)

    def get_config(self,):
        config = {'reduce_sum': self.reduce_sum,}
        base_config = super(InnerProductLayer, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class LocalActivationUnit(Layer):
    """The LocalActivationUnit used in DIN with which the representation of user interests varies adaptively given different candidate items.

      Input shape
        - A list of two 3D tensor with shape:  ``(batch_size, 1, embedding_size)`` and ``(batch_size, T, embedding_size)``

      Output shape
        - 3D tensor with shape: ``(batch_size, T, 1)``.

      Arguments
        - **hidden_size**:list of positive integer, the attention net layer number and units in each layer.

        - **activation**: Activation function to use in attention net.

        - **l2_reg**: float between 0 and 1. L2 regularizer strength applied to the kernel weights matrix of attention net.

        - **keep_prob**: float between 0 and 1. Fraction of the units to keep of attention net. 

        - **use_bn**: bool. Whether use BatchNormalization before activation or not in attention net.

        - **seed**: A Python integer to use as random seed.

      References
        - [Deep Interest Network for Click-Through Rate Prediction](https://arxiv.org/pdf/1706.06978.pdf)
    """

    def __init__(self,hidden_size, activation,l2_reg, keep_prob, use_bn,seed,**kwargs):
        self.hidden_size = hidden_size
        self.activation = activation
        self.l2_reg = l2_reg
        self.keep_prob = keep_prob
        self.use_bn = use_bn
        self.seed = seed
        super(LocalActivationUnit, self).__init__(**kwargs)

    def build(self, input_shape):

        if not isinstance(input_shape, list) or len(input_shape) != 2:
            raise ValueError('A `LocalActivationUnit` layer should be called '
                             'on a list of 2 inputs')

        if len(input_shape[0]) != 3 or len(input_shape[1]) != 3 :
                raise ValueError("Unexpected inputs dimensions %d and %d, expect to be 3 dimensions" % (len(input_shape[0]),len(input_shape[1])))

        if input_shape[0][-1]!=input_shape[1][-1] or input_shape[0][1]!=1:

            raise ValueError('A `LocalActivationUnit` layer requires '
                             'inputs of a two inputs with shape (None,1,embedding_size) and (None,T,embedding_size)'
                             'Got different shapes: %s,%s' % (input_shape))
        super(LocalActivationUnit, self).build(input_shape)  # Be sure to call this somewhere!

    def call(self, inputs,**kwargs):


        query,keys = inputs

        keys_len = keys.get_shape()[1]
        queries = K.repeat_elements(query,keys_len,1)

        att_input = K.concatenate([queries, keys, queries - keys, queries * keys], axis=-1)
        att_input = BatchNormalization()(att_input)
        att_out = MLP(self.hidden_size, self.activation, self.l2_reg, self.keep_prob, self.use_bn, seed=self.seed,name=self.name+"mlp")(att_input)
        attention_score = Dense(1, 'linear')(att_out)

        return attention_score

    def compute_output_shape(self, input_shape):
        return input_shape[1][:2] + (1,)

    def get_config(self,):
        config = {'activation': self.activation,'hidden_size':self.hidden_size, 'l2_reg':self.l2_reg, 'keep_prob':self.keep_prob,'seed': self.seed}
        base_config = super(LocalActivationUnit, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))
