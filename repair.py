import os
import cly_dcgan as GAN
import numpy as np
import cv2
import tensorflow as tf
import image_util
import configparser as cfg_parser

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

cp = cfg_parser.ConfigParser()
cp.read('net.cfg')

epochs = cp.getint('repair', 'epochs')
learning_rate = cp.getfloat('repair', 'learning_rate')
beta = cp.getfloat('repair', 'beta')
break_time = cp.getfloat('repair', 'break_time')
threshold = cp.getfloat('repair', 'threshold')
model_index = cp.getfloat('repair', 'model_index')


def init_target():
    """
    get the mask of target image according to the area to be repaired. save mask and target image as  variables
     what's the mask:the matrix has the same shape of image. but the value of each vector either 0 or 1. the value of 
     Those area prepared to repair is 1 while those constant area should be set as 0. 
    :return: 
    """
    # the scope would save the variables of mask and image
    with tf.variable_scope("target"):
        target_img, target_area = image_util.get_target_img()
        target_img = target_img.astype('float32')

        # cal the mask from target_area
        mask = np.zeros([GAN.image_width, GAN.image_height, GAN.image_depth], dtype=np.float32)
        for each_area in range(len(target_area)):
            for each_pixel in range(target_area[each_area][0], target_area[each_area][1]):
                for dim in range(GAN.image_depth):
                    mask[each_pixel // GAN.image_width][each_pixel % GAN.image_width][dim] = 1

        # save in scope
        tf.get_variable("image", [GAN.image_height, GAN.image_width, GAN.image_depth],
                        initializer=tf.constant_initializer(target_img))
        tf.get_variable("mask", [GAN.image_height, GAN.image_width, GAN.image_depth],
                        initializer=tf.constant_initializer(mask))


def get_repair_loss(inputs_noise, reuse):
    """
    we define the the loss of repair with formula:
        loss = sum{max(abs(G_x - Target_x), threshold) - threshold) for x in pixels of constant area}
        
    :param inputs_noise: the input of G (random noise)
    :param reuse: reuse the frame of G ? (we have created the structure in 'dcgan')
    :return:  
     the defination of loss
    """
    combine, generate_image, _ = get_images(inputs_noise, reuse)
    loss = tf.reduce_sum(tf.abs(tf.abs(combine - generate_image)))
    return loss


def get_images(inputs_noise, reuse):
    """
    get corresponding images
    :param inputs_noise: the input of G (random noise)
    :param reuse: reuse the frame of G ? (we have created the structure in 'dcgan')
    :return: 
     return three images,they are:
     combine: repaired image (combine the generated image and target image )
     generate_image: the image generated by G
     int_image: the image similar to target image but those areas to be repaired is filled with black
    """
    g_outputs = GAN.get_generator(inputs_noise, False, reuse)
    # reflect the output of G from [-1, 1] to [0, 1]
    generate_image = tf.multiply(tf.add(g_outputs, tf.constant(1.0)), tf.constant(0.5))

    with tf.variable_scope("target", reuse=True):
        # target image
        ready_image = tf.get_variable("image")
        # reflect the target image from [-1, 1] to [0, 1]
        ready_image = tf.multiply(tf.add(ready_image, tf.constant(1.0)), tf.constant(0.5))
        # cut the areas to be repaired from generated image
        part_repair = tf.multiply(generate_image, tf.get_variable("mask"))
        # get the int_image. do operation : (1-mask) & target image
        int_image = tf.multiply(ready_image, tf.subtract(tf.constant(1.0), tf.get_variable("mask")))
    # put the area cut from G to the black area of int_image, that's the repaired image
    combine = tf.add(part_repair, int_image)
    return combine, generate_image, int_image


def repair():
    """
    do repairing
    :return: 
    """
    inputs_noise = np.random.uniform(1, -1, size=(1, GAN.noise_size))
    inputs_noise = tf.Variable(inputs_noise.astype('float32'), name="input_noise")
    repair_loss = get_repair_loss(inputs_noise, False)
    # use Adam
    repiar_opt = tf.train.AdamOptimizer(learning_rate, beta).minimize(repair_loss, var_list=inputs_noise)

    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        # recover the structure of G from model file
        g_scope = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='generator')
        saver = tf.train.Saver(g_scope)
        saver.restore(sess, image_util.model_path + 'model-{}'.format(model_index))

        for epoch in range(epochs):
            sess.run(repiar_opt)
            if epoch % break_time == 0:
                print("in {}, loss:{}".format(epoch, sess.run(repair_loss)))
                repaired_img, generate_img, init_img = sess.run(get_images(inputs_noise, True))
                # reflect the value from [0,1] to [0,255]
                repaired_img = repaired_img[0] * 255
                generate_img = generate_img[0] * 255
                init_img = init_img * 255
                # save
                cv2.imwrite(image_util.repair_path + str(epoch) + '{}_repair.jpg'.format(epoch), repaired_img)
                cv2.imwrite(image_util.repair_path + str(epoch) + '{}_generate.jpg'.format(epoch), generate_img)
                cv2.imwrite(image_util.repair_path + 'init_img.jpg', init_img)


with tf.Graph().as_default():
    init_target()
    repair()
