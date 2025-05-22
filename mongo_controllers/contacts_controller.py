# mongo_controllers/contacts_controller.py
from flask import request, Response
from flask_restx import Namespace, Resource
from bson import json_util
from childcareconfig import child_db_instance, calculate_rolling_intervals
from dotenv import load_dotenv
import os
from pendulum import now, parse, from_timestamp

load_dotenv()
import childcareconfig
print(dir(childcareconfig))

# Initialize a Namespace for call-related API routes
contacts_namespace = Namespace("contacts", description="Contacts Management")

# device_type = "WEB"
collection_type="contacts"
db_handle = child_db_instance.childcaredb_connection()


# POST Route: Insert new contact data
@contacts_namespace.route("/insert_contacts_data")
class AddContacts(Resource):
    def post(self):
        try:
            # Get JSON data from the request body
            data = request.get_json()

            # Check if the necessary fields are provided
            if "device_id" not in data or "contacts" not in data:
                return {"message": "device_id and contacts are required in the request body"}, 400

            # Get device_id and contacts data
            device_id = data["device_id"]
            contacts = data["contacts"]

            # Validate the contacts data format (it should be a list of dictionaries)
            if not isinstance(contacts, list) or not all(isinstance(contact, dict) for contact in contacts):
                return {"message": "Contacts should be an array of objects with name and phone_number fields"}, 400

            # Insert the data into MongoDB
            contact_data = {
                "device_id": device_id,
                "contacts": contacts,
                "time": int(now().timestamp())  # Add a timestamp for when the data was inserted
            }

            collection_name = child_db_instance.device_db_collection(collection_type)[0]
            db_handle[collection_name].insert_one(contact_data)

            # Return a success response
            return {"message": "Contacts data inserted successfully"}, 201

        except Exception as e:
            print(f"Error inserting contacts data: {str(e)}")
            return {"message": "Error inserting contacts data"}, 500


# GET Route: Fetch contact data based on device_id
@contacts_namespace.route("/get_contacts_data")
class GetContacts(Resource):
    @contacts_namespace.param('device_id', 'Device ID to fetch logs for', type=str, default='5551231010')
    def get(self):
        try:
            # Get the device_id from the query parameters
            device_id = request.args.get("device_id")

            if not device_id:
                return {"message": "device_id query parameter is required"}, 400

            # Fetch the contacts data for the given device_id from MongoDB
            collection_name = child_db_instance.device_db_collection(collection_type)[0]
            result_cursor = db_handle[collection_name].find({"device_id": device_id})

            # Convert the result cursor to a list
            result = list(result_cursor)

            if result:
                # Return the result as JSON using json_util for BSON compatibility
                return Response(json_util.dumps(result), content_type="application/json")
            else:
                return {"message": f"No contacts found for device_id: {device_id}"}, 404

        except Exception as e:
            print(f"Error fetching contacts data: {str(e)}")
            return {"message": "Error fetching contacts data"}, 500
