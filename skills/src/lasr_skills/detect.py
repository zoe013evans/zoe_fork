#!/usr/bin/env python3
import cv2
import cv2_img
import rospy
import smach
from sensor_msgs.msg import Image
from lasr_vision_msgs.srv import YoloDetection

from typing import List, Union


class Detect(smach.State):
    def __init__(
        self,
        model: str = "yolov8x.pt",
        filter: Union[List[str], None] = None,
        confidence: float = 0.5,
        nms: float = 0.3,
        debug_publisher: str = "/skills/detect/debug",
    ):
        smach.State.__init__(
            self,
            outcomes=["succeeded", "failed"],
            input_keys=["img_msg"],
            output_keys=["detections"],
        )
        self.model = model
        self.filter = filter if filter is not None else []
        self.confidence = confidence
        self.nms = nms
        self.yolo = rospy.ServiceProxy("/yolov8/detect", YoloDetection)
        self.yolo.wait_for_service()
        self.debug_pub = rospy.Publisher(debug_publisher, Image, queue_size=1)

    def execute(self, userdata):
        img_msg = userdata.img_msg
        img_cv2 = cv2_img.msg_to_cv2_img(img_msg)
        try:
            result = self.yolo(img_msg, self.model, self.confidence, self.nms)
            if len(self.filter) > 0:
                result.detected_objects = [
                    det for det in result.detected_objects if det.name in self.filter
                ]
            userdata.detections = result

            # Annotate the image with the detected objects
            for det in result.detected_objects:
                x, y, w, h = det.xywh[0], det.xywh[1], det.xywh[2], det.xywh[3]
                cv2.rectangle(
                    img_cv2,
                    (x - (w // 2), y - (h // 2)),
                    (x + (w // 2), y + (h // 2)),
                    (0, 255, 0),
                    2,
                )
                cv2.putText(
                    img_cv2,
                    f"{det.name} ({det.confidence:.2f})",
                    (x - 50, y - (h // 2) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 0),
                    2,
                )

            self.debug_pub.publish(cv2_img.cv2_img_to_msg(img_cv2))

            return "succeeded"
        except rospy.ServiceException as e:
            rospy.logwarn(f"Unable to perform inference. ({str(e)})")
            return "failed"
