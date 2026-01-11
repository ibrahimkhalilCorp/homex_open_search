def success(data):
    return {"status": "success", "data": data}

def error(message):
    return {"status": "error", "message": message}
