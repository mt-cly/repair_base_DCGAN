import os
import numpy as np
import configparser as cfg_parser
import tensorflow as tf
import image_util

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

cp = cfg_parser.ConfigParser()
cp.read('net.cfg')
batch_size = cp.getint('train', 'batch_size')
noise_size = cp.getint('train', 'noise_size')
epochs = cp.getint('train', 'epochs')
n_samples = cp.getint('train', 'n_samples')
learning_rate = cp.getfloat('train', 'learning_rate')
beta1 = cp.getfloat('train', 'beta1')
max_to_keep = cp.getint('train', 'max_to_keep')
break_time = cp.getint('train', 'break_time')
image_num = cp.getint('image', 'image_num')
image_height = cp.getint('image', 'image_height')
image_width = cp.getint('image', 'image_width')
image_depth = cp.getint('image', 'image_depth')


def get_inputs():
    """
    get two placeholder
    :return: 
     inputs_real: the tensor with shape[?, image_height. image_width, image_depth], as the input of D
     iputs_noise: the tensor with shape[?, noise_size], as the input of G
    """
    inputs_real = tf.placeholder(tf.float32, [None, image_height, image_width, image_depth], name='inputs_real')
    inputs_noise = tf.placeholder(tf.float32, [None, noise_size], name='inputs_noise')
    return inputs_real, inputs_noise


def get_generator(noise, training, reuse, alpha=0.1):
    """
    define the structure of G
    
    :param noise: the input of G, the shape should be [?, noise_size]
    :param training: boolean, represent is it in training?
    :param reuse: boolean, represent does it reuse the name scope of G 'generator'
    :param alpha: a param of activation function(leaky RELU)
    
    :return: 
     outputs: the output of G with such input, with shape[?, image_height, image_width, image_depth]. the range is [-1, 1]
    """
    with tf.variable_scope("generator", reuse=reuse):
        # [?, 100]  to [?, 4x4x1024]
        # [?, 4x4x1024] to [?, 4, 4, 1024]
        # connected
        layer1 = tf.layers.dense(noise, 4 * 4 * 1024)
        layer1 = tf.reshape(layer1, [-1, 4, 4, 1024])
        layer1 = tf.layers.batch_normalization(layer1, training=training)  # BN
        layer1 = tf.maximum(alpha * layer1, layer1)  # LeakyRELU

        # [?, 4, 4, 1024] to [?, 8, 8, 512]
        # reverse conv
        # use 512 kernels with shape [3, 3, 1024], with strides=2 and padding='same'
        layer2 = tf.layers.conv2d_transpose(layer1, 512, 3, strides=2, padding='same')
        layer2 = tf.layers.batch_normalization(layer2, training=training)  # BN
        layer2 = tf.maximum(alpha * layer2, layer2)  # LeakyRELU

        # [?, 8, 8, 512] to [?, 16, 16, 256]
        # reverse conv
        # use 56 kernels with shape [3, 3, 512], with strides=2 and padding='same'
        layer3 = tf.layers.conv2d_transpose(layer2, 256, 3, strides=2, padding='same')
        layer3 = tf.layers.batch_normalization(layer3, training=training)  # BN
        layer3 = tf.maximum(alpha * layer3, layer3)  # LeakyRELU

        # [?, 16, 16, 256] to [?, 32, 32, 128]
        # reverse conv
        # use 128 kernels with shape [3, 3, 256], with strides=2 and padding='same'
        layer4 = tf.layers.conv2d_transpose(layer3, 128, 3, strides=2, padding='same')
        layer4 = tf.layers.batch_normalization(layer4, training=training)  # BN
        layer4 = tf.maximum(alpha * layer4, layer4)  # LeakyRELU

        # [?, 32, 32, 128] to [?, 64, 64, 3(image_depth)]
        # reverse conv
        # use 3 kernels with shape [3, 3, 128], with strides=2 and padding='same'
        logits = tf.layers.conv2d_transpose(layer4, image_depth, 3, strides=2, padding='same')
        outputs = tf.tanh(logits)  # use tanh as activation function without BN, reflect the result to [-1.0, 1.0]

        return outputs


def get_discriminator(input_imgs, training, reuse, alpha=0.1):
    """
    define the structure of G
    
    :param input_imgs: the input of D,the input image can be from train_data or generated by G. the range should 
                        be [-1,1], so if the input is real image, you need to do some reflection prior.
                        the shape should be [?, image_height, image_width, image_depth]
    :param training: just like the statement shows above
    :param reuse: 
    :param alpha: 
    :return: 
     logits: the output of D, but without the last operation -- 'sigmod', so the range of that is R. why we return such 
            a useless value? Due to the mechanism of sigmoid_cross_entropy_with_logits, the function's param-limitation.
     outputs: the final output of D, the range is [0, 1] because of reflection of 'sigmoid'
    """

    # the structure of D is similar to G
    with tf.variable_scope("discriminator", reuse=reuse):
        # [?, 64, 64, 3(image_depth)]  to [?, 32, 32, 64]
        # conv
        # use 64 kernels with shape [5, 5, 3], with strides=2 and padding='same'
        layer1 = tf.layers.conv2d(input_imgs, 64, 5, strides=2, padding='same')
        # Attention, don't pass data for BN. I don't know why, but everyone do it like this. hhhh
        layer1 = tf.maximum(alpha * layer1, layer1)  # LeakyRELU

        # [?, 32, 32, 64] to [?, 16, 16, 128]
        # conv
        # use 128 kernels with shape [5, 5, 64], with strides=2 and padding='same'
        layer2 = tf.layers.conv2d(layer1, 128, 5, strides=2, padding='same')
        layer2 = tf.layers.batch_normalization(layer2, training=training)  # BN
        layer2 = tf.maximum(alpha * layer2, layer2)  # LeakyRELU

        # [?, 16, 16, 128] to [?, 8, 8, 256]
        # conv
        # use 256 kernels with shape [5, 5, 128], with strides=2 and padding='same'
        layer3 = tf.layers.conv2d(layer2, 256, 5, strides=2, padding='same')
        layer3 = tf.layers.batch_normalization(layer3, training=training)  # BN
        layer3 = tf.maximum(alpha * layer3, layer3)  # LeakyRELU

        # [?, 8, 8, 256] to [?, 4, 4, 512]
        # conv
        # uee 512kernels with shape [5, 5, 256], with strides=2 and padding='same'
        layer4 = tf.layers.conv2d(layer3, 512, 5, strides=2, padding='same')
        layer4 = tf.layers.batch_normalization(layer4, training=training)  # BN
        layer4 = tf.maximum(alpha * layer4, layer4)  # LeakyRELU

        # [?, 4, 4, 512] to  [?, 4x4x512]
        # [?, 4, 4, 512] to  [?, 1]
        # connected
        flatten = tf.reshape(layer4, (-1, 4 * 4 * 512))
        logits = tf.layers.dense(flatten, 1)  # catch the logits here
        outputs = tf.sigmoid(logits)  # sigmod, reflect the result to [-1.0, 1.0]

        return logits, outputs


def get_loss(noise, real_imgs, smooth=0.05):
    """
    calculate the loss with given data. the loss can be divided for two parts -- the loss of D and the loss of G. 
    D_loss symbols the level of distinction of given image, while the G_loss symbols the ability of fake image.
    D_loss is constituted of D_real_loss() and D_fake_loss.
    in paper, G: minimize{ log(1-D(G(z))) } and the loss of D: maximize{ log(D(x)) + log(1 - D(G(z))) } 
    the detail of  function 'sigmoid_cross_entropy_with_logits(logits, label)' :
       y = label    p = sigmod(logits)    loss = -[y * ln(p) + (1-y) * ln(1-p)]
    
    :param noise: the input of G, the noise prepared for G.
    :param real_imgs: the real images from train_data, whose range has been reflected from [0, 255] to [-1, 1]
                        in each channel 
    :param smooth: a param for prevent from overfitting, set the label value with (1-smooth) but not 1.
    :return: 
     return a tuple contain two part: (G_loss, D_loss)
    """

    # ========================begin: calculate g_loss ========================
    g_outputs = get_generator(noise, True, False)
    d_logits_fake, d_outputs_fake = get_discriminator(g_outputs, True, False)
    """ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!  
    G_loss: minimize[log(1-D(G(z)))] to minimize[- log(D(G(z)))] 
    The G_loss in paper is defined as log(1-D(G(z))), however it not suitable with sigmoid activation function.
                ▽log(1-D(G(z))) = ▽log(1-sigmoid(logits))
                              = [-sigmoid(logits)*(1-sigmoid(logits))] / [1-sigmoid(logits)]
                              = -sigmoid(logits)
    Imagine such a situation:
     When the G is very weak, D can point out those fake image easily -- D(G(z)) or sigmoid(logits) is closed to 0.
     We surely hope the gradient can be bigger so that G can change more. However, the vaule of formula above is:
                ▽log(1-D(G(z))) = -sigmoid(logits)
                              ≈ -0
     Gradient is closed to zero. That's really a bad news. So we do some transform:
     From minimize[log(1-D(G(z)))] to minimize[- log(D(G(z))] 
     The gradient is closed to one when G is weak and closed to zero when G can fake image well.
                ▽log(-D(G(z))) = ▽log(-sigmoid(logits))
                             = [-sigmoid(logits) * (1-sigmoid(logits))] / [-sigmoid(logits)]
                             = 1-sigmoid(logits)
    """
    g_loss = tf.nn.sigmoid_cross_entropy_with_logits(logits=d_logits_fake,
                                                     labels=tf.ones_like(d_outputs_fake) * (1 - smooth))
    g_loss = tf.reduce_mean(g_loss)
    # ========================= end =========================

    # ======================== begin: calculate d_loss ========================
    # the structure of G has been defined, so we just set reuse=True
    d_logits_real, d_outputs_real = get_discriminator(real_imgs, True, True)
    """!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    D_real_loss: maximize(log(D(z)) to minimize(-log(D(z))
    In paper, the target is to maximize(log(D(z)), because optimizers in tensorflow are all designed to reduce 
    loss, reduce the value of given formula, so we change the target from maximize(log(D(z)) to minimize(-log(D(z)). 
    that enough, because we find  when D is weak and D(z) closed to 0, the gradient of logists is closed to 1.   
    """
    d_loss_real = tf.nn.sigmoid_cross_entropy_with_logits(logits=d_logits_real,
                                                          labels=tf.ones_like(d_outputs_real) * (1 - smooth))
    d_loss_real = tf.reduce_mean(d_loss_real)

    """!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    D_fake_loss: maximize(log(1 - D(G(z)))) to minimize(-log(1 - D(G(z))))
    In paper, the D_fake_loss symbols the ability of picking up fake image of D. When G is very weak, 
    D can point out those fake image easily. Now, the gradient for G should be bigger but that's opposite from D, the D
    is good enough, the gradient for D should be smaller. This formula can be suitable without do any change more. 
    """
    d_loss_fake = tf.nn.sigmoid_cross_entropy_with_logits(logits=d_logits_fake, labels=tf.zeros_like(d_outputs_fake))
    d_loss_fake = tf.reduce_mean(d_loss_fake)

    d_loss = tf.add(d_loss_real, d_loss_fake)
    # ========================= end =========================

    return g_loss, d_loss


def get_optimizer(g_loss, d_loss):
    """
    Define the optimizer for minimizing the loss. Here we pick the AdamOptimizer. Surely you can replace with other OPT.
    
    :param g_loss: loss of G net. calculated by 'get_loss'
    :param d_loss: loss of D net. calculated by 'get_loss'
    :return: 
     g_opt: Optimizer for g_loss
     d_opt: Optimizer for d_loss
    """

    # 'tf.trainable_variables()' would return variables trainable in graph. We divide variables to G_vars and D_vars.
    train_vars = tf.trainable_variables()
    g_vars = [var for var in train_vars if var.name.startswith("generator")]
    d_vars = [var for var in train_vars if var.name.startswith("discriminator")]

    with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
        g_opt = tf.train.AdamOptimizer(learning_rate=learning_rate, beta1=beta1).minimize(g_loss, var_list=g_vars)
        d_opt = tf.train.AdamOptimizer(learning_rate=learning_rate, beta1=beta1).minimize(d_loss, var_list=d_vars)

    return g_opt, d_opt


def show_generator_output(sess, noise_holder):
    """
    get the outputs of G, the input of G will be create with 'random' in function inside.
    :param sess:  session 
    :param noise_holder: the placeholder of input of G
    :return: 
     samples: imgs generated by G, but the range of value is still [-1, 1]
    """
    batch_noise = np.random.uniform(-1, 1, size=(n_samples, noise_size))
    samples = sess.run(get_generator(noise_holder, False, True), feed_dict={noise_holder: batch_noise})
    return samples


def train():
    """
    the training part of project, we will do such: define graph, send data, optimize, save model... 
    :return: 
    
    """

    # define graph of DCGAN
    inputs_real, inputs_noise = get_inputs()
    g_loss, d_loss = get_loss(inputs_noise, inputs_real)
    g_train_opt, d_train_opt = get_optimizer(g_loss, d_loss)

    # feed with data -- start to train
    with tf.Session() as sess:
        begin_time = 0
        saver = tf.train.Saver(max_to_keep=max_to_keep)
        sess.run(tf.global_variables_initializer())
        #
        # =============== recover the net param from saved model for further training =================
        # begin_time = 10
        # recover = tf.train.import_meta_graph(image_util.model_path+'model-{}.meta'.format(begin_time))
        # recover.restore(sess, tf.train.latest_checkpoint(image_util.model_path))
        # =============================================================================================

        for epoch in range(begin_time, epochs):
            images = image_util.get_imgs(image_num)

            for batch_i in range(images.shape[0]  // batch_size):
                print("training in (epoch = {}, batch = {})".format(epoch, batch_i))
                batch_images = images[batch_i * batch_size: (batch_i + 1) * batch_size]

                # ============= we choose the image data sequential, you can also select with random ==============
                # batch_images = images.tolist()
                # batch_images = random.sample(batch_images, batch_size)
                # batch_images = np.array(batch_images)
                # batch_images.reshape(-1,64,64,3)
                # ==================================================================================================

                # reflect the range of input of G from [0 1] to [-1, 1]
                batch_images = batch_images * 2 - 1
                batch_noise = np.random.uniform(-1, 1, size=(batch_size, noise_size))

                # doing k iteration for G after doing one iteration for D was recommended in paper. Here k=1
                sess.run(d_train_opt, feed_dict={inputs_real: batch_images, inputs_noise: batch_noise})
                sess.run(g_train_opt, feed_dict={inputs_real: batch_images, inputs_noise: batch_noise})

            train_loss_g = g_loss.eval({inputs_real: batch_images, inputs_noise: batch_noise})
            train_loss_d = d_loss.eval({inputs_real: batch_images, inputs_noise: batch_noise})
            print("g_loss:", train_loss_g)
            print("d_loss:", train_loss_d)
            # save images generated by G after each epoch
            samples = show_generator_output(sess, inputs_noise)
            image_util.plot_images(epoch, samples)

            # save model
            if epoch % break_time == 0:
                saver.save(sess, image_util.model_path+'model', global_step=epoch)

if __name__ == '__main__':
    with tf.Graph().as_default():
        train()
