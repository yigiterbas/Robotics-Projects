#!/usr/bin/env python

import math
import numpy
import time
from threading import Thread, Lock

import rospy
import tf
from geometry_msgs.msg import Transform
from sensor_msgs.msg import JointState
from std_msgs.msg import Float32
from urdf_parser_py.urdf import URDF

def S_matrix(w):
    S = numpy.zeros((3,3))
    S[0,1] = -w[2]
    S[0,2] =  w[1]
    S[1,0] =  w[2]
    S[1,2] = -w[0]
    S[2,0] = -w[1]
    S[2,1] =  w[0]
    return S

# This is the function that must be filled in as part of the Project.
def cartesian_control(joint_transforms, b_T_ee_current, b_T_ee_desired,
                      red_control, q_current, q0_desired):
    num_joints = len(joint_transforms)
    dq = numpy.zeros(num_joints)
    #-------------------- Fill my code here ---------------------------
    rospy.logdebug('\n\nnumber of joints :\t%s\n\n', num_joints)
    # Prints the arguments for debugging
    # joint_transforms: list containing the transforms of all the joints with
    # respect to the base frame
    #rospy.logdebug('\n\njoint_transforms\n\n %s\n\n', joint_transforms)
    #rospy.logdebug('\n\nb_T_ee_current\n\n%s\n\n', b_T_ee_current)
    #rospy.logdebug('\n\nb_T_ee_desired\n\n%s\n\n', b_T_ee_desired)

    # compute the desired change in end-effector pose from b_T_ee_current to b_T_ee_desired
    # the end-effector is in his own coordinate frame
    # is a vector that represents the desired displacement
    ee_T_b = tf.transformations.inverse_matrix(b_T_ee_current)
    ee_T_ee = numpy.dot(ee_T_b, b_T_ee_desired)
    rospy.logdebug('\n\nb_T_ee :\n\n%s\n\n', ee_T_ee)
    # get the translation part
    b_t_ee = tf.transformations.translation_from_matrix(ee_T_ee)
    rospy.logdebug('\n\nTranslation\t%s\n\n', b_t_ee)
    # get the rotation part
    b_R_ee = ee_T_ee[:3,:3]
    rospy.logdebug('\n\nRotation\n\n%s\n\n', b_R_ee)
    # Obtain the necessary angles in a tuple for each axis
    angle, axis = rotation_from_matrix(ee_T_ee)
    rospy.logdebug('\n\nangle\t%s\t\taxis\t%s\n\n', angle,axis)
    ROT = numpy.dot(angle,axis)
    rospy.logdebug('\n\nROT\t%s\n\n', ROT)
    # Invert the rotation matrix
    # to obtain ee_R_b = (b_R_ee)^-1 = (b_R_ee).T 
    # because rotation matrices are ORTHOGONAL.
    ee_R_b = tf.transformations.inverse_matrix(b_R_ee)
    rospy.logdebug('\n\nInverse matrix :\n\n%s\n\n', ee_R_b)

    # convert the desired change into a desired end-effector velocity
    # (the simplest form is to use a PROPORTIONAL CONTROLLER)

    # Change of the end-effector in the base coordinate frame
    lin_gain = 3
    rot_gain = 1.5

    delta_X = numpy.append(b_t_ee * lin_gain, ROT * rot_gain)
    rospy.logdebug('\n\nDelta X\t%s\n\n', delta_X)

    # velocity controller in end-effector space
    proportional_gain = 1
    x_dot = proportional_gain * delta_X

    # normalize the desired change
    '''
    if numpy.linalg.norm(x_dot) > 1.0:
        x_dot /= max(x_dot)
	'''
    rospy.logdebug('\n\nx_dot\t%s\n\n', x_dot)

    # NUMERICALLY compute the robot Jacobian. For each joint compute the matrix
    # that relates the velocity of that joint to the velocity of the end-effector
    # in its own coordinate frame. Assemble the last column of all these matrices
    # to construct the Jacobian.

    # This tells you what a specific joint is going to do to the end effector,
    # in the reference frame of the joint

    # The Jacobian is a matrix that relates the velocity of that joint to the 
    # velocity of the end-effector in its own coordinate frame
    J = numpy.empty((6, 0))

    for j in range(num_joints):
        # b_T_j (from base to joint j)
        b_T_j = joint_transforms[j]
        #rospy.logdebug('\n\n[b_T_j]\n\n%s\n\n', b_T_j)
        
        # Transformation to obtain the velocity in its own coordinate frame
        j_T_b = tf.transformations.inverse_matrix(b_T_j)
        j_T_ee = numpy.dot(j_T_b, b_T_ee_current)
        # invert the previous homogeneous matrix
        ee_T_j = tf.transformations.inverse_matrix(j_T_ee)
        # Same approach
        #ee_T_j = numpy.dot(ee_T_b, b_T_j)

        ee_R_j = ee_T_j[:3,:3]

        j_t_ee = tf.transformations.translation_from_matrix(j_T_ee)
        S = S_matrix(j_t_ee)
        
        # This matrix is only applicable for revolute joints
        Vj = numpy.append(
            numpy.append(
                ee_R_j,
                numpy.dot(-ee_R_j, S),
                axis=1), 
            numpy.append(
                numpy.zeros([3,3]),
                ee_R_j,
                axis=1), 
            axis=0)
        #rospy.logdebug('\n\n[Vj]\n\n%s\n\n', Vj)

        # Assuming that all the joints are revolute, we only use the z component
        J = numpy.column_stack((J, Vj[:,5])) 

    rospy.logdebug('\n\nJacobian\n\n%s\n\n', J)
	
    # Compute the pseudo-inverse of the Jacobian to avoid numerical
    # issues that can arise from small singular values
    # Use the pseudo-inverse of the Jacobian to map from end-effector velocity to
    # joint velocities.
    J_pinv = numpy.linalg.pinv(J, rcond=1e-2)
    rospy.logdebug('\n\nJacobian Pseudo-inverse\n\n%s\n\n', J_pinv)

    # map from end-effector velocity to joint velocities (angular in the z axis for all joints)
    dq = numpy.dot(J_pinv, x_dot)

    if red_control == True:
    	# implements the null-space control on the first joint
        # This can be implemented in any moment because the robot
        # has more joints than DOF

        # q_current: list of all the current joint positions
        rospy.logdebug('\n\nq_current\t%s\n\n', q_current)
        # q0_desired: desired position of the first joint to be used as
        # the secondary objective for null-space control. Again, the goal
        # of the secondary, null-space controller is to make the value of
        # the first joint be as close as possible to q0_desired, while not
        # affecting the pose of the end-effector.
        rospy.logdebug('\n\nq0_desired\t%s\n\n', q0_desired)

        # find a joint velocity that brings the joint closer to the secondary objective.
        # use the Jacobian and its pseudo-inverse to project this velocity into the
        # Jacobian nullspace. It must be used the 'exact' version of the Jacobian
        # pseudo-inverse, not its 'safe' version. 
        J_pinv = numpy.linalg.pinv(J, rcond=0)
        dq_n = numpy.dot(
            numpy.identity(7) - numpy.dot(J_pinv, J), 
            numpy.array([q0_desired - q_current[0],0,0,0,0,0,0]))
        #Then add the result to the joint velocities obtained for the primary objective
        dq = numpy.dot(J_pinv, x_dot) + dq_n
     
    rospy.logdebug('\n\ndq\t%s\n\n', dq)
	#----------------------------------------------------------------------
    return dq
    
def convert_from_message(t):
    trans = tf.transformations.translation_matrix((t.translation.x,
                                                  t.translation.y,
                                                  t.translation.z))
    rot = tf.transformations.quaternion_matrix((t.rotation.x,
                                                t.rotation.y,
                                                t.rotation.z,
                                                t.rotation.w))
    T = numpy.dot(trans,rot)
    return T

# Returns the angle-axis representation of the rotation contained in the input matrix
# Use like this:
# angle, axis = rotation_from_matrix(R)
def rotation_from_matrix(matrix):
    R = numpy.array(matrix, dtype=numpy.float64, copy=False)
    R33 = R[:3, :3]
    # axis: unit eigenvector of R33 corresponding to eigenvalue of 1
    l, W = numpy.linalg.eig(R33.T)
    i = numpy.where(abs(numpy.real(l) - 1.0) < 1e-8)[0]
    if not len(i):
        raise ValueError("no unit eigenvector corresponding to eigenvalue 1")
    axis = numpy.real(W[:, i[-1]]).squeeze()
    # point: unit eigenvector of R33 corresponding to eigenvalue of 1
    l, Q = numpy.linalg.eig(R)
    i = numpy.where(abs(numpy.real(l) - 1.0) < 1e-8)[0]
    if not len(i):
        raise ValueError("no unit eigenvector corresponding to eigenvalue 1")
    # rotation angle depending on axis
    cosa = (numpy.trace(R33) - 1.0) / 2.0
    if abs(axis[2]) > 1e-8:
        sina = (R[1, 0] + (cosa-1.0)*axis[0]*axis[1]) / axis[2]
    elif abs(axis[1]) > 1e-8:
        sina = (R[0, 2] + (cosa-1.0)*axis[0]*axis[2]) / axis[1]
    else:
        sina = (R[2, 1] + (cosa-1.0)*axis[1]*axis[2]) / axis[0]
    angle = math.atan2(sina, cosa)
    return angle, axis

class CartesianControl(object):

    #Initialization
    def __init__(self):
        #Loads the robot model, which contains the robot's kinematics information
        self.robot = URDF.from_parameter_server()

        #Subscribes to information about what the current joint values are.
        rospy.Subscriber("/joint_states", JointState, self.joint_callback)

        #Subscribes to command for end-effector pose
        rospy.Subscriber("/cartesian_command", Transform, self.command_callback)

        #Subscribes to command for redundant dof
        rospy.Subscriber("/redundancy_command", Float32, self.redundancy_callback)

        # Publishes desired joint velocities
        self.pub_vel = rospy.Publisher("/joint_velocities", JointState, queue_size=1)

        #This is where we hold the most recent joint transforms
        self.joint_transforms = []
        self.q_current = []
        self.x_current = tf.transformations.identity_matrix()
        self.R_base = tf.transformations.identity_matrix()
        self.x_target = tf.transformations.identity_matrix()
        self.q0_desired = 0
        self.last_command_time = 0
        self.last_red_command_time = 0

        # Initialize timer that will trigger callbacks
        self.mutex = Lock()
        self.timer = rospy.Timer(rospy.Duration(0.1), self.timer_callback)

    def command_callback(self, command):
        self.mutex.acquire()
        self.x_target = convert_from_message(command)
        self.last_command_time = time.time()
        self.mutex.release()

    def redundancy_callback(self, command):
        self.mutex.acquire()
        self.q0_desired = command.data
        self.last_red_command_time = time.time()
        self.mutex.release()        
        
    def timer_callback(self, event):
        msg = JointState()
        self.mutex.acquire()
        if time.time() - self.last_command_time < 0.5:
            dq = cartesian_control(self.joint_transforms, 
                                   self.x_current, self.x_target,
                                   False, self.q_current, self.q0_desired)
            msg.velocity = dq
        elif time.time() - self.last_red_command_time < 0.5:
            dq = cartesian_control(self.joint_transforms, 
                                   self.x_current, self.x_current,
                                   True, self.q_current, self.q0_desired)
            msg.velocity = dq
        else:            
            msg.velocity = numpy.zeros(7)
        self.mutex.release()
        self.pub_vel.publish(msg)
        
    def joint_callback(self, joint_values):
        root = self.robot.get_root()
        T = tf.transformations.identity_matrix()
        self.mutex.acquire()
        self.joint_transforms = []
        self.q_current = joint_values.position
        self.process_link_recursive(root, T, joint_values)
        self.mutex.release()

    def align_with_z(self, axis):
        T = tf.transformations.identity_matrix()
        z = numpy.array([0,0,1])
        x = numpy.array([1,0,0])
        dot = numpy.dot(z,axis)
        if dot == 1: return T
        if dot == -1: return tf.transformation.rotation_matrix(math.pi, x)
        rot_axis = numpy.cross(z, axis)
        angle = math.acos(dot)
        return tf.transformations.rotation_matrix(angle, rot_axis)

    def process_link_recursive(self, link, T, joint_values):
        if link not in self.robot.child_map: 
            self.x_current = T
            return
        for i in range(0,len(self.robot.child_map[link])):
            (joint_name, next_link) = self.robot.child_map[link][i]
            if joint_name not in self.robot.joint_map:
                rospy.logerror("Joint not found in map")
                continue
            current_joint = self.robot.joint_map[joint_name]        

            trans_matrix = tf.transformations.translation_matrix((current_joint.origin.xyz[0], 
                                                                  current_joint.origin.xyz[1],
                                                                  current_joint.origin.xyz[2]))
            rot_matrix = tf.transformations.euler_matrix(current_joint.origin.rpy[0], 
                                                         current_joint.origin.rpy[1],
                                                         current_joint.origin.rpy[2], 'rxyz')
            origin_T = numpy.dot(trans_matrix, rot_matrix)
            current_joint_T = numpy.dot(T, origin_T)
            if current_joint.type != 'fixed':
                if current_joint.name not in joint_values.name:
                    rospy.logerror("Joint not found in list")
                    continue
                # compute transform that aligns rotation axis with z
                aligned_joint_T = numpy.dot(current_joint_T, self.align_with_z(current_joint.axis))
                self.joint_transforms.append(aligned_joint_T)
                index = joint_values.name.index(current_joint.name)
                angle = joint_values.position[index]
                joint_rot_T = tf.transformations.rotation_matrix(angle, 
                                                                 numpy.asarray(current_joint.axis))
                next_link_T = numpy.dot(current_joint_T, joint_rot_T) 
            else:
                next_link_T = current_joint_T

            self.process_link_recursive(next_link, next_link_T, joint_values)
        
if __name__ == '__main__':
    rospy.init_node('cartesian_control', anonymous=True)
    cc = CartesianControl()
    rospy.spin()
