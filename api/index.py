from http.server import BaseHTTPRequestHandler
import json
import numpy as np
import sys
import os
import resource
import traceback

# Load model parameters
current_dir = os.path.dirname(os.path.realpath(__file__))
model_path = os.path.join(current_dir, 'digit_recognizer_model.json')

try:
    with open(model_path, 'r') as f:
        model_params = json.load(f)
    print("Model parameters loaded successfully", file=sys.stderr)
except FileNotFoundError:
    print(f"Error: Model file not found at {model_path}", file=sys.stderr)
except json.JSONDecodeError:
    print(f"Error: Invalid JSON format in {model_path}", file=sys.stderr)
except Exception as e:
    print(f"Error loading model parameters: {str(e)}", file=sys.stderr)

W1 = np.array(model_params['W1'])
b1 = np.array(model_params['b1'])
W2 = np.array(model_params['W2'])
b2 = np.array(model_params['b2'])

def ReLU(Z):
    return np.maximum(Z, 0)

def softmax(Z):
    A = np.exp(Z) / np.sum(np.exp(Z))
    return A

def forward_prop(W1, b1, W2, b2, X):
    Z1 = W1.dot(X) + b1
    A1 = ReLU(Z1)
    Z2 = W2.dot(A1) + b2
    A2 = softmax(Z2)
    return Z1, A1, Z2, A2

def get_predictions(A2):
    return np.argmax(A2, 0)

def ReLU_deriv(Z):
    return Z > 0

def one_hot(Y):
    one_hot_Y = np.zeros((10, 1))
    one_hot_Y[Y] = 1
    return one_hot_Y

def backward_prop(Z1, A1, Z2, A2, W1, W2, X, Y):
    m = X.shape[1]
    one_hot_Y = one_hot(Y)
    dZ2 = A2 - one_hot_Y
    dW2 = 1 / m * dZ2.dot(A1.T)
    db2 = 1 / m * np.sum(dZ2, axis=1, keepdims=True)
    dZ1 = W2.T.dot(dZ2) * ReLU_deriv(Z1)
    dW1 = 1 / m * dZ1.dot(X.T)
    db1 = 1 / m * np.sum(dZ1, axis=1, keepdims=True)
    return dW1, db1, dW2, db2

def update_params(W1, b1, W2, b2, dW1, db1, dW2, db2, alpha):
    W1 = W1 - alpha * dW1
    b1 = b1 - alpha * db1    
    W2 = W2 - alpha * dW2  
    b2 = b2 - alpha * db2    
    return W1, b1, W2, b2

def log_memory_usage():
    memory_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Convert to MB
    print(f"Current memory usage: {memory_usage:.2f} MB", file=sys.stderr)
    
    # Vercel's memory limit for serverless functions (adjust if needed)
    memory_limit = 1024  # 1024 MB = 1 GB
    if memory_usage > memory_limit * 0.9:  # Warning at 90% usage
        print(f"WARNING: Approaching memory limit. Usage: {memory_usage:.2f} MB / {memory_limit} MB", file=sys.stderr)

def handler(event, context):
    print("Received event:", json.dumps(event), file=sys.stderr)
    print("Current working directory:", os.getcwd(), file=sys.stderr)
    print("Contents of current directory:", os.listdir('.'), file=sys.stderr)

    log_memory_usage()

    try:
        if event['path'] == '/api/predict':
            body = json.loads(event['body'])
            image_data = np.array(body['image']).reshape(784, 1) / 255.0

            Z1, A1, Z2, A2 = forward_prop(W1, b1, W2, b2, image_data)
            prediction = int(get_predictions(A2)[0])

            response = {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'prediction': prediction})
            }
            return response

        elif event['path'] == '/api/train':
            body = json.loads(event['body'])
            image_data = np.array(body['image']).reshape(784, 1) / 255.0
            label = int(body['label'])

            global W1, b1, W2, b2 

            Z1, A1, Z2, A2 = forward_prop(W1, b1, W2, b2, image_data)
            dW1, db1, dW2, db2 = backward_prop(Z1, A1, Z2, A2, W1, W2, image_data, np.array([label]))
            W1, b1, W2, b2 = update_params(W1, b1, W2, b2, dW1, db1, dW2, db2, 0.1)  # Adjust learning rate as needed

            response = {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'status': 'Model trained on one sample'})
            }
            return response

        else:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Not Found'})
            }

    except Exception as e:
        print("Error occurred:", str(e), file=sys.stderr)
        print("Error traceback:", traceback.format_exc(), file=sys.stderr)
        log_memory_usage()
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e), 'traceback': traceback.format_exc()})
        }

class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        event = {'body': post_data.decode('utf-8'), 'path': self.path}
        response = handler(event, None)
        
        self.send_response(response['statusCode'])
        for key, value in response['headers'].items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(response['body'].encode('utf-8'))

if __name__ == "__main__":
    from http.server import HTTPServer
    server = HTTPServer(('localhost', 8000), MockHandler)
    print('Starting server on http://localhost:8000')
    server.serve_forever()