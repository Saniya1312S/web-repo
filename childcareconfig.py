#childcareconfig
# from re import M
from dotenv import load_dotenv, find_dotenv
from pendulum import now
from sqlalchemy import create_engine
import pandas as pd
import os, logging, secrets, base64
from pymongo import MongoClient
from datetime import datetime, date
from pendulum import now, parse
logger = logging.getLogger()
load_dotenv()

# User Management Database Configuration
DATABASE_DIALECT = os.getenv('DATABASE_DIALECT')
DATABASE_USER = os.getenv('DATABASE_USER')
DATABASE_PASSWORD = os.getenv('DATABASE_PASSWORD')
DATABASE_HOST = os.getenv('DATABASE_HOST')
DATABASE_PORT = os.getenv('DATABASE_PORT')
DATABASE_DB = os.getenv('DATABASE_DB')

# MongoDB Connection
# Device type is going to defined at the begining of appliction
# For web application, device_type will be 'WEB'
# For child application, device_type will be 'CHILD'
# For parent application, device_type will be 'PARENT'
# For testing application, device_type will be 'WEB'
# device_type = "WEB"
device_type= os.getenv('DEVICE_TYPE')


def device_db_handle(device_type):
    MongoDB_RO_USER = os.getenv('MongoDB_RO_USER')
    MongoDB_RO_PASSWORD = os.getenv('MongoDB_RO_PASSWORD')
    if device_type == 'WEB':
        # Backend MongoDB Database Configuration 
        MongoDB_DIALECT = os.getenv('Backend_MongoDB_DIALECT')
        MongoDB_HOST = os.getenv('Backend_MongoDB_HOST')
        MongoDB_DB = os.getenv('Backend_MongoDB_DB')
        MongoDB_ADMIN_USER = os.getenv('Backend_MongoDB_ADMIN_USER')
        MongoDB_ADMIN_PASSWORD = os.getenv('Backend_MongoDB_ADMIN_PASSWORD')
        MongoDB_time_interval = os.getenv('Backend_time_interval')
        MongoDB_data_retention_days = os.getenv('Backend_data_retention_days')
    elif device_type == 'CHILD':
        MongoDB_DIALECT = os.getenv('Child_MongoDB_DIALECT')
        MongoDB_HOST = os.getenv('Child_MongoDB_HOST')
        MongoDB_DB = os.getenv('Child_MongoDB_DB')
        MongoDB_ADMIN_USER = os.getenv('Child_MongoDB_ADMIN_USER')
        MongoDB_ADMIN_PASSWORD = os.getenv('Child_MongoDB_ADMIN_PASSWORD')
        MongoDB_time_interval = os.getenv('Child_time_interval')
        MongoDB_data_retention_days = os.getenv('Child_data_retention_days')
    elif device_type == 'PARENT':
        MongoDB_DIALECT = os.getenv('Realtime_MongoDB_DIALECT')
        MongoDB_HOST = os.getenv('Realtime_MongoDB_HOST')
        MongoDB_DB = os.getenv('Realtime_MongoDB_DB')
        MongoDB_ADMIN_USER = os.getenv('Realtime_MongoDB_ADMIN_USER')
        MongoDB_ADMIN_PASSWORD = os.getenv('Realtime_MongoDB_ADMIN_PASSWORD')  
        MongoDB_time_interval = os.getenv('Realtime_time_interval')
        MongoDB_data_retention_days = os.getenv('Realtime_data_retention_days')      
    else: 
        MongoDB_DIALECT == None
        MongoDB_HOST == None
        MongoDB_DB == None
        MongoDB_ADMIN_USER == None
        MongoDB_ADMIN_PASSWORD == None
        MongoDB_time_interval == None
        MongoDB_data_retention_days == None
    return (MongoDB_DIALECT, MongoDB_HOST, MongoDB_DB, MongoDB_ADMIN_USER, MongoDB_ADMIN_PASSWORD, 
            MongoDB_time_interval, MongoDB_data_retention_days, MongoDB_RO_USER, MongoDB_RO_PASSWORD)




@staticmethod
def calculate_rolling_intervals(device_id, start_time, MongoDB_time_interval):
    try:
        # Ensure start_time is a Pendulum DateTime object (it should be, as it's parsed)
        # start_time=  parse("2025-01-31T18:30:00.000")
        Current_time = start_time
        if Current_time > now():
            logger.error("Current_time is greater than now")
            return False

        interval_days = float(MongoDB_time_interval)
        start_time_calc = Current_time.subtract(seconds=interval_days * 86400)
        end_time = Current_time
        print(start_time_calc)
        print(end_time)

        # # Calculate the start_time and end_time based on the interval
        # start_time_calc = Current_time.subtract(days=interval_days)  # Subtract interval from current time
        # end_time_calc = Current_time  # End time is the current time
        
        # Build the aggregation filter. Here we assume that your MongoDB documents store the time
        # as an integer timestamp. Adjust as needed if you store DateTime objects.
        filter = [
            {"$match": {"device_id": str(device_id)}},
            {
                "$addFields": {
                    "start_time": start_time_calc.int_timestamp,
                    "end_time": end_time.int_timestamp
                }
            },
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            {"$gte": ["$time", "$start_time"]},
                            {"$lte": ["$time", "$end_time"]}
                        ]
                    }
                }
            }
        ]
        return filter
    except Exception as e:
        print(f"Error creating filter: {str(e)}")
        return False



## Creation of JWT Token Secret Key with 32 Bytes with Expiry of 1 day 
# Define the JWT Token Secret Key
def generate_jwt_secret_key(length=32):
    random_bytes = secrets.token_bytes(length)
    secret_key = base64.urlsafe_b64encode(random_bytes).decode('utf-8')
    return secret_key

# secret_key = generate_jwt_secret_key()
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
# JWT_SECRET_KEY = secret_key
# print(JWT_SECRET_KEY)
# JWT_TOKEN_LOCATION = ""
# JWT_TOKEN_LOCATION = ["headers"]
# JWT_CLIENT_CLAIM = "user_id"   # default = sub
# print(JWT_SECRET_KEY)

CACHE_CONFIG ={
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
}
DATA_CACHE_CONFIG = CACHE_CONFIG

# User Management Database Configuration
class authdb:
    def __init__(self,
                 DATABASE_DIALECT,
                 DATABASE_USER,
                 DATABASE_PASSWORD,
                 DATABASE_HOST,
                 DATABASE_PORT,
                 DATABASE_DB):
        # MySQL Connection
        self.DATABASE_DIALECT = DATABASE_DIALECT
        self.DATABASE_USER = DATABASE_USER
        self.DATABASE_PASSWORD = DATABASE_PASSWORD
        self.DATABASE_HOST = DATABASE_HOST
        self.DATABASE_PORT = DATABASE_PORT
        self.DATABASE_DB = DATABASE_DB

    def __str__(self):
        if DATABASE_DIALECT is None:
            logger.error("DATABASE_DIALECT environment variable not found.")
            exit(1)
        SQLALCHEMY_DATABASE_URI = f"{self.DATABASE_DIALECT}://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_DB}"
        return SQLALCHEMY_DATABASE_URI

    def authdb_connection(self):
        # Db Connection 
        connsql = self.__str__()
        try:
            # Db Engine Connection 
            conn_engine = create_engine(connsql)
            print("Connecting to database successfully")
        except Exception as e:
            logger.error(f"Could not connect to database: {str(e)}")
            exit(1)
        return conn_engine

    def view_all_data(self, sql_query):
        conn_engine = self.authdb_connection()
        try:
            all_data = pd.read_sql(sql_query, conn_engine)
            return (all_data)
        except Exception as e:
            logger.error(f"Could not view all data: {str(e)}")
            exit(1)
        finally:
            conn_engine.dispose()

db_config = authdb(
    DATABASE_DIALECT=DATABASE_DIALECT,
    DATABASE_USER=DATABASE_USER,
    DATABASE_PASSWORD=DATABASE_PASSWORD,
    DATABASE_HOST=DATABASE_HOST,
    DATABASE_PORT=DATABASE_PORT,
    DATABASE_DB=DATABASE_DB
)

# Store the generated SQLAlchemy URI in a variable
SQLALCHEMY_DATABASE_URI = str(db_config)

class childcaredb:
    def __init__(self, device_type):
        # Get MongoDB details from device_db_handle function
        MongoDB_DIALECT, MongoDB_HOST, MongoDB_DB, MongoDB_ADMIN_USER, MongoDB_ADMIN_PASSWORD, \
        MongoDB_time_interval, MongoDB_data_retention_days, MongoDB_RO_USER, MongoDB_RO_PASSWORD = device_db_handle(device_type)
        
        # MongoDB Connection
        self.device_type = device_type  # Save device_type as an instance variable
        self.MongoDB_DIALECT = MongoDB_DIALECT
        self.MongoDB_HOST = MongoDB_HOST
        self.MongoDB_ADMIN_USER = MongoDB_ADMIN_USER
        self.MongoDB_ADMIN_PASSWORD = MongoDB_ADMIN_PASSWORD
        self.MongoDB_DB = MongoDB_DB
        self.MongoDB_time_interval = MongoDB_time_interval
        self.MongoDB_data_retention_days = MongoDB_data_retention_days
        self.MongoDB_RO_USER = MongoDB_RO_USER
        self.MongoDB_RO_PASSWORD = MongoDB_RO_PASSWORD
        self._childcaredb_handle = None  # To store the DB handle
    
    def __str__(self):
        if self.MongoDB_DIALECT is None:
            logger.error("MongoDB_DIALECT environment variable not found.")
            exit(1)
        if self.device_type == 'PARENT':
            MongoDB_uri = f"{self.MongoDB_DIALECT}://{self.MongoDB_RO_USER}:{self.MongoDB_RO_PASSWORD}@{self.MongoDB_HOST}"    
        else:    
            MongoDB_uri = f"{self.MongoDB_DIALECT}://{self.MongoDB_ADMIN_USER}:{self.MongoDB_ADMIN_PASSWORD}@{self.MongoDB_HOST}"
        # print(MongoDB_uri) 
        return MongoDB_uri
        
    def childcaredb_connection(self):
        try:
            # Create MongoDB client using device_type from instance variable
            _childcaredb_client = MongoClient(self.__str__())  # No need to pass device_type here
            self._childcaredb_handle = _childcaredb_client[self.MongoDB_DB]  # Store the DB handle as an instance variable
            # print("Connected to MongoDB database successfully")
            return self._childcaredb_handle  # Return the db handle without closing the client
        except Exception as e:
            logger.error(f"Could not connect to MongoDB database: {str(e)}")
            exit(1)

    # Device Database Collection
    def device_db_collection(self, collection_type: None):
        geofence_collection_name = os.getenv('GEOFENCE_COLLECTION')
        # Collection Names
        if collection_type == 'location':
            collection_name = os.getenv('LOCATION_COLLECTION')
        elif collection_type == 'family':
            collection_name = os.getenv('FAMILY_COLLECTION')
        elif collection_type == 'device':
            collection_name = os.getenv('DEVICE_COLLECTION')
        elif collection_type == 'app_usage':
            collection_name = os.getenv('APP_USAGE_COLLECTION')
        elif collection_type == 'call':
            collection_name = os.getenv('CALL_COLLECTION')
        elif collection_type == 'message':
            collection_name = os.getenv('MESSAGE_COLLECTION')
        elif collection_type == 'social_media':
            collection_name = os.getenv('SOCIAL_MEDIA_COLLECTION')
        elif collection_type == 'browser':
            collection_name = os.getenv('BROWSER_HISTORY')
        elif collection_type == 'contacts':
            collection_name = os.getenv('CONTACTS_COLLECTION')
        elif collection_type == 'mask':
            collection_name = os.getenv('FAMILY_MASK_COLLECTION')
        else: 
            collection_name = None
        return collection_name, geofence_collection_name

    # Create Database Collection if not exists
    def create_collection_if_not_exists(self, collection_name):
        try:
            collection = self._childcaredb_handle.create_collection(collection_name)
            print(f"Collection '{collection_name}' created successfully.")
        except Exception:
            # print(f"Collection '{collection_name}' already exists.")
            collection = self._childcaredb_handle[collection_name]
        return collection

    # Insert One Document in Collection
    def insert_one_document(self, collection_name, data):
        try:
            collection = self._childcaredb_handle[collection_name]
            document = collection.insert_one(data)
            print(f"Document '{document.inserted_id}' inserted successfully.")
            return document.inserted_id
        except Exception as e:
            print(f"Error inserting document: {str(e)}")
            return False

    # Insert Multiple Documents in Collection
    def insert_multiple_documents(self, collection_name, data):
        try:
            collection = self._childcaredb_handle[collection_name]
            document = collection.insert_many(data)
            print(f"Documents '{document.inserted_ids}' inserted successfully.")
            return document.inserted_ids
        except Exception as e:
            print(f"Error inserting documents: {str(e)}")
            return False

    # View All Data in Collection
    def get_device_data(self, collection_name, device_id):
        try:
            collection = self._childcaredb_handle[collection_name]
            key = {'device_id': device_id}
            data = collection.find(key)
            return data
        except Exception as e:
            print(f"Error viewing all data: {str(e)}")
            return False

    # get filter datafor Aggregation
    def get_device_filter_data(self, collection_name, device_id, Current_time):
        try:
            collection = self._childcaredb_handle[collection_name]
            filter = calculate_rolling_intervals(device_id, Current_time, self.MongoDB_time_interval)
            data = collection.find_one(filter)
            return data
        except Exception as e:  
            print(f"Error creating filter: {str(e)}")
            return False

    # Create Pipeline for Aggregation
    def create_device_pipeline(self, collection_name, device_id, Current_time):
        try:
            collection = self._childcaredb_handle[collection_name]
            filter = calculate_rolling_intervals(device_id, Current_time, self.MongoDB_time_interval)
            pipeline = [
                {
                    "$match": filter
                }
            ]
            data = collection.aggregate(pipeline)
            return data
        except Exception as e:
            print(f"Error creating pipeline: {str(e)}")
            return False
        
    def update_one_document(self, collection_name, filter_query, update_query, upsert=False, array_filters=None):
        try:
            collection = self._childcaredb_handle[collection_name]
            update_args = {
                "filter": filter_query,
                "update": update_query,
                "upsert": upsert
            }
            if array_filters:
                update_args["array_filters"] = array_filters
            
            result = collection.update_one(**update_args)
            print(f"Matched count: {result.matched_count}, Modified count: {result.modified_count}")
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception as e:
            print(f"Error updating document: {str(e)}")
            return False

          
    def find_one_document(self, collection_name, query):
        collection = self._childcaredb_handle[collection_name]
        return collection.find_one(query)

        



        
# Initialize MongoDB connection
child_db_instance = childcaredb(device_type)
MongoDB_uri = str(child_db_instance)
db_handle = child_db_instance.childcaredb_connection()


# Now use the MongoDB_time_interval from the instance
MongoDB_time_interval = child_db_instance.MongoDB_time_interval
print(f"MongoDB_time_interval: {MongoDB_time_interval}")



