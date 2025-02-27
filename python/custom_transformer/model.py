# Copyright 2021 The KServe Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import base64
import io
from typing import Dict

import numpy

from PIL import Image
from torchvision import transforms
from kserve.grpc.grpc_predict_v2_pb2 import ModelInferRequest, ModelInferResponse

from kserve import Model, ModelServer, model_server
from kserve.model import PredictorProtocol


def image_transform(instance):
    """converts the input image of Bytes Array into Tensor
    Args:
        request input instance: The request input instance for image.
    Returns:
        List: Returns the data key's value and converts that into a list
        after converting it into a tensor
    """
    image_processing = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])
    byte_array = base64.b64decode(instance["image"]["b64"])
    image = Image.open(io.BytesIO(byte_array))
    tensor = image_processing(image).numpy()
    print(tensor.shape)
    return tensor


class ImageTransformer(Model):
    def __init__(self, name: str, predictor_host: str, protocol: str):
        super().__init__(name)
        self.predictor_host = predictor_host
        self.protocol = protocol
        self.ready = True

    def preprocess(self, payload: Dict, headers: Dict[str, str] = None) -> ModelInferRequest:
        # Input follows the Tensorflow V1 HTTP API for binary values
        # https://www.tensorflow.org/tfx/serving/api_rest#encoding_binary_values
        input_tensors = [image_transform(instance) for instance in payload["instances"]]

        # Transform to KServe v1/v2 inference protocol
        if self.protocol == PredictorProtocol.GRPC_V2.value:
            return self.v2_request_transform(numpy.asarray(input_tensors))
        else:
            inputs = [{"data": input_tensor.tolist()} for input_tensor in input_tensors]
            payload = {"instances": inputs}
            return payload

    def v2_request_transform(self, input_tensors):
        request = ModelInferRequest()
        request.model_name = self.name
        tensor = {
            'name': "INPUT__0",
            'shape': input_tensors.shape,
            'datatype': "FP32",
        }
        request.inputs.extend([tensor])
        request.raw_input_contents.extend([input_tensors.tobytes()])
        return request

    def postprocess(self, infer_response: ModelInferResponse, headers: Dict[str, str] = None) -> Dict:
        if self.protocol == PredictorProtocol.GRPC_V2.value:
            res = super.postprocess(infer_response, headers)
            return {"predictions": res["contents"]["fp32_contents"]}
        else:
            return infer_response


parser = argparse.ArgumentParser(parents=[model_server.parser])
parser.add_argument(
    "--predictor_host", help="The URL for the model predict function", required=True
)
parser.add_argument(
    "--protocol", help="The protocol for the predictor", default="v1"
)
parser.add_argument(
    "--model_name", help="The name that the model is served under."
)
args, _ = parser.parse_known_args()

if __name__ == "__main__":
    model = ImageTransformer(args.model_name, predictor_host=args.predictor_host,
                             protocol=args.protocol)
    ModelServer(workers=1).start([model])
