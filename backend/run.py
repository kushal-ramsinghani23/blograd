from flask import Flask
from app.routes.urls import demoBlue

app = Flask(__name__)
app.register_blueprint(demoBlue)

if __name__ == "__main__":
    app.run(debug=True)
