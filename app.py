# app.py
from flask import Flask
from flask_cors import CORS # type: ignore
from flask_jwt_extended import JWTManager
from flask_restx import Api
from flask_pymongo import PyMongo
from childcareconfig import JWT_SECRET_KEY, SQLALCHEMY_DATABASE_URI
from extensions import db
from controllers.usercontroller import userauth_namespace
from mongo_controllers.app_usage_controller import app_usage_namespace
from mongo_controllers.call_controller import call_namespace
from mongo_controllers.app_usage_controller import app_usage_namespace
from mongo_controllers.message_controller import message_namespace
from mongo_controllers.location_controller import location_namespace
from mongo_controllers.browser_controller import browser_namespace
from mongo_controllers.social_media_controller import social_media_namespace
from mongo_controllers.contacts_controller import contacts_namespace
from childcareconfig import MongoDB_uri
app = Flask(__name__)
CORS(app)    

# Configure MySQL and JWT settings
app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY

app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure MongoDB (adjust the URI as needed)
app.config['MONGO_URI'] = MongoDB_uri

# Initialize extensions
jwt = JWTManager(app)
db.init_app(app)
mongo = PyMongo(app)  # This creates MongoDB connection

# Initialize Flask-RESTx API
api = Api(app)

# Register MySQL (User) namespace
api.add_namespace(userauth_namespace, path='/user')

# Register MongoDB namespaces
api.add_namespace(userauth_namespace)
api.add_namespace(app_usage_namespace)
api.add_namespace(call_namespace)
api.add_namespace(message_namespace)
api.add_namespace(location_namespace)
api.add_namespace(browser_namespace)
api.add_namespace(social_media_namespace)
api.add_namespace(contacts_namespace)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
 



