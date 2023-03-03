import json

def _send(socket, data):
    try:
        serialized = json.dumps((data))
    except (TypeError, ValueError):
        raise Exception('You can only send JSON-serializable data')
    socket.sendall(serialized.encode('utf-8'))


def _recv(socket):
            data = socket.recv(4000).decode("utf-8")
            try:
                deserialized = json.loads(data)
            except (TypeError, ValueError):
                raise Exception('Data received was not in JSON format')
            return deserialized



