#extensions.py

from flask import Flask
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from flask_restx import Api
from flask_bcrypt import Bcrypt
import childcareconfig as childcareconfig

# Initialize Flask app
app = Flask(__name__)

# Initialize extensions
db = SQLAlchemy()

# Configure Swagger UI
authorizations = {
    'Bearer Auth': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'Add a JWT token to the header with Bearer prefix. Example: "Bearer abcde12345"'
    }
}

# Creating API instance and defining API version and title
api = Api(
    # app,
    version='1.0', 
    title="ChildCare", 
    description='ChildCare monitoring API',
    authorizations=authorizations,
    security='Bearer Auth',
    doc='/swagger',
    prefix='/api/v1'
)



jwt = JWTManager(app)
bcrypt = Bcrypt()


