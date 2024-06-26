#!/usr/bin/env python3
import smach
from pal_startup_msgs.srv import StartupStart, StartupStop
import rosservice
import rospy
import numpy as np
from sensor_msgs.msg import PointCloud2
from tiago_controllers.helpers.pose_helpers import get_pose_from_param
from lasr_object_detection_yolo.detect_objects_v8 import (
    detect_objects,
    perform_detection,
    debug,
    estimate_pose,
)

HORIZONTAL = 0.8
VERTICAL = 0.3


def euclidean_distance(point1, point2):
    return np.sqrt(
        (point1[0] - point2[0]) ** 2
        + (point1[1] - point2[1]) ** 2
        + (point1[2] - point2[2]) ** 2
    )


class Encounter(smach.State):
    def __init__(self, default):
        smach.State.__init__(self, outcomes=["success", "failed"])

        self.default = default

        # stop head manager
        if "/pal_startup_control/stop" in rosservice.get_service_list():
            self.stop_head_manager = rospy.ServiceProxy(
                "/pal_startup_control/stop", StartupStop
            )
            self.start_head_manager = rospy.ServiceProxy(
                "/pal_startup_control/start", StartupStart
            )

    def order_indices(self, current, previous):
        if len(current) == 1 and len(previous) == 1:
            return [0]

        indices = []
        if len(current) == len(previous):
            for person_i in range(len(current)):
                diffs = list(
                    map(
                        lambda lo: np.linalg.norm(
                            np.array(current[person_i]) - np.array(lo)
                        ),
                        previous,
                    )
                )
                indices.append(diffs.index(min(diffs)))

        return indices

    def execute(self, userdata):
        self.default.controllers.head_controller.look_straight()
        self.default.controllers.torso_controller.sync_reach_to(0.25)

        movement = [
            self.default.controllers.head_controller.look_straight,
            self.default.controllers.head_controller.look_right,
            self.default.controllers.head_controller.look_left,
        ]

        self.default.voice.speak(
            "This is the encounter situation. I will be looking for someone who is excited to see me!!"
        )

        pose = get_pose_from_param("/phase3_lift/pose")
        polygon = rospy.get_param("/corners_arena")
        headPoint = None
        is_found = False

        currentFrame = 0
        FRAME_PER_FACE = 10
        frames_locations = []
        current_head_pose = 0

        while not is_found:
            rospy.sleep(2)
            pcl_msg = rospy.wait_for_message(
                "/xtion/depth_registered/points", PointCloud2
            )
            detections, im = perform_detection(
                self.default, pcl_msg, polygon, ["person"]
            )

            pos_people = []
            for j, person in detections:
                person = person.tolist()
                pos_people.append([person[0], person[1]])

            frames_locations.append(pos_people)
            rospy.logwarn(frames_locations)
            if (
                len(frames_locations) == 2
                and len(frames_locations[0]) > 0
                and len(frames_locations[0]) == len(frames_locations[1])
            ):
                rospy.loginfo("TRUE")
                # swap if needed
                match_indices = self.order_indices(
                    frames_locations[1], frames_locations[0]
                )

                if not (match_indices == [0]):
                    frames_locations[1] = [
                        frames_locations[1][match_i] for match_i in match_indices
                    ]

                # CALC VECS
                rospy.loginfo(len(frames_locations[1]))
                for loc_vect in range(len(frames_locations[1])):
                    a2 = np.array(frames_locations[1][loc_vect]) - np.array(
                        frames_locations[0][loc_vect]
                    )
                    if np.linalg.norm(a2) > 0.05:
                        rospy.loginfo(f"Norm { np.linalg.norm(a2)}")
                        headPoint = np.array(frames_locations[1][loc_vect])
                        is_found = True
                    else:
                        rospy.loginfo(f"STATIC PERSON - {np.linalg.norm(a2)}")

            if len(frames_locations) > 1:
                frames_locations = frames_locations[1:]

            if currentFrame >= FRAME_PER_FACE:
                currentFrame = 0
                current_head_pose += 1
                movement[current_head_pose]()
            else:
                currentFrame += 1

        print(headPoint)
        self.default.controllers.base_controller.sync_face_to(
            headPoint[0], headPoint[1]
        )

        self.default.controllers.torso_controller.sync_reach_to(0.2)
        self.default.controllers.head_controller.look_straight()

        self.default.voice.speak(
            "You seem very excited to see me. I am also excited to see you."
        )
        return "success"


if __name__ == "__main__":
    rospy.init_node("encounter", anonymous=True)
