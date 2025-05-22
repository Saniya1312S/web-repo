# mongo_controllers/location_controller.py
import os
from flask import request, Response, jsonify
from flask_restx import Namespace, Resource
from bson import json_util
from childcareconfig import childcaredb,child_db_instance, calculate_rolling_intervals, device_type # Assuming you have childcaredb in childcareconfig
from datetime import datetime
import redis
from math import radians, sin, cos, sqrt, atan2
from pendulum import from_timestamp, parse
import json

# Initialize a Namespace for location-related API routes
location_namespace = Namespace("location", description="Location Management")

# device_type = "WEB"
collection_type = "location"
db_handle = child_db_instance.childcaredb_connection()

cache = redis.StrictRedis(host="localhost", port=6379, db=0)


# Haversine formula to calculate distance between two lat/lon points
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in kilometers
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# Lambda function to check if the point is inside a geofence
is_inside_geofence = lambda lat, lon, geofence, address=None: (
    haversine(lat, lon, geofence["center"]["latitude"], geofence["center"]["longitude"]) <= geofence["radius_km"]
    or (address and geofence["address"].lower() in address.lower())
)

# Fetch geofences from Redis or MongoDB
def get_geofences(device_id):
    cache_key = f"geofences:{device_id}"
    try:
        geofences = cache.get(cache_key)
        if geofences:
            return json.loads(geofences)
    except redis.exceptions.ConnectionError as e:
        print(f"Redis connection error: {e}")

    # Fallback to MongoDB
    device_collection = child_db_instance.device_db_collection("device")[0]  # Adjust collection name as needed
    device = child_db_instance.get_device_data(device_collection, device_id)
    geofences = device.get("geofences", []) if device else []
    return geofences

# Fetch family_id from the device collection
def get_family_id(device_id):
    device_collection = child_db_instance.device_db_collection("device")[0]  # Adjust collection name as needed
    try:
        device_data = child_db_instance.get_device_data(device_collection, device_id)
        if not device_data:
            return None, f"Device with ID {device_id} not found"

        family_id = device_data.get("family_id")
        if not family_id:
            return None, f"Family ID not found for device ID {device_id}"

        return family_id, None
    except Exception as e:
        return None, f"Database query failed: {str(e)}"
@location_namespace.route('/single_location_insert')
class InsertSingleLocationData(Resource):
    @location_namespace.doc(responses={
        201: 'Document inserted or updated successfully',
        400: 'Invalid input data',
        500: 'Operation failed'
    }) 
    def post(self):
        try:
            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            required_fields = ["device_id", "time", "latitude", "longitude", "address", "location_source", "from_time"]
            if not all(field in data for field in required_fields):
                return {"message": "Missing required fields"}, 400

            device_id = str(data["device_id"])
            time_stamp = data["time"]
            new_from_time = data["from_time"]

            location_entry = {
                "location": {
                    "latitude": data["latitude"],
                    "longitude": data["longitude"],
                    "address": data["address"]
                },
                "location_source": data["location_source"],
                "from_time": new_from_time,
                "to_time": None
            }

            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            if not isinstance(collection_name, str):
                return {"message": "Invalid collection name"}, 500

            query = {
                "device_id": device_id,
                "time": time_stamp
            }

            # Step 1a: Get last location entry with to_time = None
            doc = child_db_instance._childcaredb_handle[collection_name].find_one(query)
            if doc and "location_history" in doc:
                last_entry = next((entry for entry in reversed(doc["location_history"]) if entry.get("to_time") is None), None)
                if last_entry:
                    last_from_time = last_entry["from_time"]
                    duration = new_from_time - last_from_time  # in milliseconds

                    # Step 1b: Update the last entry's to_time and duration
                    update_previous = {
                        "$set": {
                            "location_history.$[last].to_time": new_from_time,
                            "location_history.$[last].duration": duration
                        }
                    }
                    array_filters = [{"last.to_time": None}]
                    child_db_instance.update_one_document(
                        collection_name,
                        query,
                        update_previous,
                        upsert=False,
                        array_filters=array_filters
                    )

            # Step 2: Insert the new location entry
            update = {
                "$push": {
                    "location_history": location_entry
                },
                "$setOnInsert": {
                    "device_id": device_id,
                    "time": time_stamp
                }
            }

            result = child_db_instance.update_one_document(
                collection_name,
                query,
                update,
                upsert=True
            )

            if result:
                return {"message": "Document inserted or updated successfully"}, 201
            else:
                return {"message": "Update/Insert failed"}, 500

        except Exception as e:
            print("Error during insert/update:", str(e))
            return {"message": f"Error during insert/update: {str(e)}"}, 500



@location_namespace.route('/multiple_location_insert')
class InsertMultipleLocationData(Resource):
    @location_namespace.doc(responses={
        201: 'Documents inserted successfully',
        400: 'Invalid input data',
        500: 'Insertion failed'
    })
    def post(self):
        try:
            # Parse the incoming JSON data
            data = request.get_json()

            # Print incoming data to debug
            print("Received data:", data)

            if not data:
                return {"message": "No data provided"}, 400

            # Validate the required fields for multiple documents
            if 'locations' not in data:
                return {"message": "Missing required field 'locations' in request"}, 400

            locations_data = data['locations']

            # Prepare a list to store all documents to be inserted
            documents_to_insert = []

            # Process each location entry
            for location_data in locations_data:
                # Validate required fields in each location data
                if not all(k in location_data for k in ("device_id", "time", "location_history")):
                    return {"message": "Missing required fields in a location entry"}, 400

                location_doc = {
                    "device_id": str(location_data['device_id']),  # Ensure device_id is a string
                    "time": location_data['time'],  # Assuming time is in a valid format (e.g., integer)
                    "location_history": []
                }

                # Validate and process each location entry
                for loc in location_data['location_history']:
                    if not all(k in loc for k in ("location", "location_source", "duration", "from_time", "to_time", "geofence")):
                        return {"message": "Invalid location_history format, missing required fields"}, 400

                    location = loc['location']
                    if not all(k in location for k in ("latitude", "longitude", "address")):
                        return {"message": "Invalid location format, missing required fields"}, 400
                    
                    location_doc['location_history'].append({
                        "location": {
                            "latitude": location['latitude'],
                            "longitude": location['longitude'],
                            "address": location['address']
                        },
                        "location_source": loc['location_source'],
                        "duration": loc['duration'],
                        "from_time": loc['from_time'],
                        "to_time": loc['to_time'],
                        "geofence": loc['geofence']
                    })

                # Add the validated document to the list of documents to insert
                documents_to_insert.append(location_doc)

            # Log the documents being inserted to debug the structure
            print("Documents to be inserted:", documents_to_insert)

            # Check if the collection name is a valid string
            collection_name, _ = child_db_instance.device_db_collection(collection_type)  # Assuming you want to insert into 'location_data' collection
            print("Collection name:", collection_name)

            if not isinstance(collection_name, str):
                return {"message": "Invalid collection name"}, 500

            # Insert multiple documents into MongoDB
            inserted_ids = child_db_instance.insert_multiple_documents(collection_name, documents_to_insert)
            if inserted_ids:
                return {"message": "Documents inserted successfully", "inserted_ids": [str(id) for id in inserted_ids]}, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            # Log the error for debugging
            print("Error during insertion:", str(e))
            return {"message": f"Error during insertion: {str(e)}"}, 500

# Route for retrieving filtered location data using a static timestamp
@location_namespace.route('/get_location_filter_data')
class LocationFilterData(Resource):
    @location_namespace.doc(responses={
        200: 'Returns filtered location data.',
        400: 'device_id query parameter is required.',
        404: 'No matching data found using filter.',
        500: 'Error fetching location data.'
    })
    @location_namespace.param('device_id', 'Device ID to fetch location data for', type=str)
    def get(self):
        device_id = request.args.get("device_id")
        if not device_id:
            return {"message": "device_id query parameter is required"}, 400

        # Use the static time "2025-01-31T18:30:00.000" (adjusted as needed)
        static_time = parse("2025-01-31T18:30:00.000")

        try:
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            
            # Convert MongoDB_time_interval to float to avoid type errors.
            interval = float(child_db_instance.MongoDB_time_interval)
            # Call the function to create a filter
            rolling_filter = calculate_rolling_intervals(device_id, static_time, interval)
            if not rolling_filter:
                return {"message": "Error creating filter"}, 500

            # Execute the aggregation pipeline using aggregate()
            result_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)
            result = list(result_cursor)
            if result:
                return Response(json_util.dumps(result), content_type="application/json", status=200)
            else:
                return {"message": "No matching data found using filter"}, 404

        except Exception as e:
            return {"message": str(e)}, 500

# Route for retrieving all locations
@location_namespace.route('/get_all_locations')
class GetAllLocations(Resource):
    @location_namespace.doc(responses={
        200: 'Returns all location data for the specified device_id.',
        400: 'device_id is required.',
        404: 'No location data found for the given device_id.'
    })
    @location_namespace.param('device_id', 'Device ID to fetch location data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        if not device_id:
            return {"message": "device_id is required"}, 400
        
        # Fetch the location data from the MongoDB collection
        collection_name = child_db_instance.device_db_collection(collection_type)[0]  # Assuming 'location' is the collection type
        try:
            data = child_db_instance.get_device_data(collection_name, device_id)
            if data:
                # Convert the MongoDB cursor to a list and then to JSON
                return Response(json_util.dumps(data), content_type='application/json')
            else:
                return {"message": "No location data found for the given device_id"}, 404
        except Exception as e:
            return {"message": f"Error fetching location data: {str(e)}"}, 500

def get_paginated_location_data(device_id, page, per_page, pagination_type):
    try:
        # Static timestamp for reference (can be adjusted as needed)
        static_time = from_timestamp(1738367999)  # Example static 'end_time' for location history logs
        
        # Fetch MongoDB_time_interval, set to 1 day if not available
        try:
            interval_days = float(os.getenv("MongoDB_time_interval", 1))
        except Exception as e:
            return {"message": "MongoDB_time_interval is not set or invalid"}, 500
        
        # Handle pagination types: 'previous', 'current', 'next'
        if pagination_type == 'previous':
            start_time = static_time.subtract(days=interval_days * 2)
        elif pagination_type == 'next':
            start_time = static_time.add(days=interval_days * 2)
        else:  # 'current'
            start_time = static_time.subtract(days=interval_days)

        # Create filter for location history records based on start_time
        rolling_filter = calculate_rolling_intervals(device_id, start_time, interval_days)
        if not rolling_filter:
            return {"message": "Error creating filter"}, 500

        collection_name = child_db_instance.device_db_collection(collection_type)[0]

        # Fetch location data from MongoDB using aggregation pipeline
        data_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)
        all_location_history = []

        # Flatten the location_history arrays from MongoDB documents
        for doc in data_cursor:
            if 'location_history' in doc:
                all_location_history.extend(doc['location_history'])

        # Total count of location history records
        total_count = len(all_location_history)
        total_pages = (total_count // per_page) + (1 if total_count % per_page > 0 else 0)

        # Pagination logic
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        paginated_data = all_location_history[start_index:end_index]

        if paginated_data:
            # Paginated response
            response = {
                "data": json_util.dumps(paginated_data),  # Serialize location history data
                "total_count": total_count,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages
            }
            return Response(response['data'], content_type="application/json")
        else:
            return {
                "message": f"No data found for the date {start_time.format('YYYY-MM-DD')}. Try checking for a different date."
            }, 200
    except Exception as e:
        return {"message": f"Error fetching location data: {str(e)}"}, 500


# API Endpoints

@location_namespace.route('/get_paginated_location_data')
class GetPaginatedLocationDataCurrent(Resource):
    @location_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @location_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @location_namespace.param('device_id', 'Device ID to fetch location data for', type=str, default='5551231010')
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        if not device_id:
            return {"message": "device_id is required"}, 400
        
        # Call the common method with 'current' pagination type
        return get_paginated_location_data(device_id, page, per_page, 'current')


@location_namespace.route('/get_paginated_location_data_previous')
class GetPaginatedLocationDataPrevious(Resource):
    @location_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @location_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @location_namespace.param('device_id', 'Device ID to fetch location data for', type=str, default='5551231010')
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        if not device_id:
            return {"message": "device_id is required"}, 400
        
        # Call the common method with 'previous' pagination type
        return get_paginated_location_data(device_id, page, per_page, 'previous')


@location_namespace.route('/get_paginated_location_data_next')
class GetPaginatedLocationDataNext(Resource):
    @location_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @location_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @location_namespace.param('device_id', 'Device ID to fetch location data for', type=str, default='5551231010')
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        if not device_id:
            return {"message": "device_id is required"}, 400
        
        # Call the common method with 'next' pagination type
        return get_paginated_location_data(device_id, page, per_page, 'next')

 














# # Route for inserting a single location
# @location_namespace.route('/single_location_insert')
# class InsertSingleLocation(Resource):
#     @location_namespace.doc(responses={
#         201: 'Location data inserted successfully.',
#         400: 'Device ID is required.',
#         404: 'Device not found.',
#         500: 'Failed to insert data.'
#     })
#     def post(self):
#         try:
#             location_data = request.get_json()
#             if not location_data:
#                 return {"status": "error", "message": "No data provided"}, 400

#             # Validate required fields
#             device_id = location_data.get("device_id")
#             if not device_id:
#                 return {"status": "error", "message": "Device ID is required"}, 400

#             # Fetch family_id using the helper method
#             family_id, error = get_family_id(device_id)
#             if error:
#                 return {"status": "error", "message": error}, 404

#             # Extract location details
#             latitude = location_data.get("latitude")
#             longitude = location_data.get("longitude")
#             address = location_data.get("address", "")
#             if not latitude or not longitude:
#                 return {"status": "error", "message": "Latitude and longitude are required"}, 400

#             # Fetch geofences
#             geofences = get_geofences(device_id)
#             geofence_status = "outside"
#             for geofence in geofences:
#                 if is_inside_geofence(latitude, longitude, geofence, address):
#                     geofence_status = "inside"
#                     break

#             # Transform the data into the required format
#             transformed_data = {
#                 "family_id": family_id,
#                 "device_id": device_id,
#                 "location": {
#                     "latitude": latitude,
#                     "longitude": longitude,
#                     "address": address,
#                 },
#                 "location_source": location_data.get("location_source"),
#                 "time": location_data.get("time"),
#                 "geofence": geofence_status,
#             }

#             # Insert data into the MongoDB collection
#             collection_name, _ = child_db_instance.device_db_collection(collection_type)
#             result = child_db_instance.insert_one_document(collection_name, transformed_data)
#             transformed_data["_id"] = str(result.inserted_id)  # Convert ObjectId to string

#             # Return the response
#             return jsonify({
#                 "status": "success",
#                 "message": "Location data inserted successfully.",
#                 "data": transformed_data
#             })

#         except Exception as e:
#             return {"status": "error", "message": f"Failed to insert data: {str(e)}"}, 500
# @location_namespace.route('/multiple_location_insert')
# class InsertMultipleLocationData(Resource):
#     @location_namespace.doc(responses={
#         201: 'Documents inserted successfully',
#         400: 'Invalid input data',
#         500: 'Insertion failed'
#     })
#     def post(self):
#         try:
#             # Parse the incoming JSON data
#             data = request.get_json()

#             # Print incoming data to debug
#             print("Received data:", data)

#             if not data:
#                 return {"message": "No data provided"}, 400

#             # Validate the required fields for multiple documents
#             if 'locations' not in data:
#                 return {"message": "Missing required field 'locations' in request"}, 400

#             locations_data = data['locations']

#             # Prepare a list to store all documents to be inserted
#             documents_to_insert = []

#             # Process each location entry
#             for location_data in locations_data:
#                 # Validate required fields in each location data
#                 if not all(k in location_data for k in ("device_id", "time", "location_history")):
#                     return {"message": "Missing required fields in a location entry"}, 400

#                 location_doc = {
#                     "device_id": str(location_data['device_id']),  # Ensure device_id is a string
#                     "time": location_data['time'],  # Assuming time is in a valid format (e.g., integer)
#                     "location_history": []
#                 }

#                 # Validate and process each location entry
#                 for loc in location_data['location_history']:
#                     if not all(k in loc for k in ("location", "location_source", "duration", "from_time", "to_time", "geofence")):
#                         return {"message": "Invalid location_history format, missing required fields"}, 400

#                     location = loc['location']
#                     if not all(k in location for k in ("latitude", "longitude", "address")):
#                         return {"message": "Invalid location format, missing required fields"}, 400
                    
#                     location_doc['location_history'].append({
#                         "location": {
#                             "latitude": location['latitude'],
#                             "longitude": location['longitude'],
#                             "address": location['address']
#                         },
#                         "location_source": loc['location_source'],
#                         "duration": loc['duration'],
#                         "from_time": loc['from_time'],
#                         "to_time": loc['to_time'],
#                         "geofence": loc['geofence']
#                     })

#                 # Add the validated document to the list of documents to insert
#                 documents_to_insert.append(location_doc)

#             # Log the documents being inserted to debug the structure
#             print("Documents to be inserted:", documents_to_insert)

#             # Check if the collection name is a valid string
#             collection_name, _ = child_db_instance.device_db_collection("location_data")  # Assuming you want to insert into 'location_data' collection
#             print("Collection name:", collection_name)

#             if not isinstance(collection_name, str):
#                 return {"message": "Invalid collection name"}, 500

#             # Insert multiple documents into MongoDB
#             inserted_ids = child_db_instance.insert_multiple_documents(collection_name, documents_to_insert)
#             if inserted_ids:
#                 return {"message": "Documents inserted successfully", "inserted_ids": [str(id) for id in inserted_ids]}, 201
#             else:
#                 return {"message": "Insertion failed"}, 500

#         except Exception as e:
#             # Log the error for debugging
#             print("Error during insertion:", str(e))
#             return {"message": f"Error during insertion: {str(e)}"}, 500



# @location_namespace.route("/post-static-geofence")
# class PostStaticGeofence(Resource):
#     def post(self):
#         # Parse request data
#         data = request.get_json()
#         user_confirmation = data.get("confirmation")  # "Yes" or "No"
#         device_id = data.get("device_id")
 
#         # Validate input
#         if not user_confirmation or not device_id:
#             return {"status": "fail", "message": "Confirmation and device_id are required."}, 400
 
#         if user_confirmation.lower() != "yes":
#             return {"status": "cancelled", "message": "User declined to save the static geofence."}, 200
 
#         # Static geofence data
#         static_geofence = {
#             "address": "HITEC City, Hyderabad, Telangana",
#             "center": {
#                 "latitude": 17.4498,
#                 "longitude": 78.382
#             },
#             "radius_km": 0.1
#         }
 
#         # Update geofence in device_data collection
#         update_result = device_collection.update_one(
#             {"device.device_id": device_id},
#             {"$push": {"geofences": static_geofence}}
#         )
 
#         if update_result.modified_count == 0:
#             return {"status": "fail", "message": f"No device found with device_id {device_id}."}, 404
 
#         return {
#             "status": "success",
#             "message": "Static geofence added successfully."
#         }, 201




# @location_namespace.route("/add-safe-not")
# class PostStaticGeofence(Resource):
#     def post(self):
#         # Parse request data
#         data = request.get_json()
#         user_confirmation = data.get("confirmation")  # "Yes" or "No"
#         device_id = data.get("device_id")
#         address = data.get("address")  # Get the address from the request
#         latitude = data.get("latitude")  # Get latitude
#         longitude = data.get("longitude")  # Get longitude

#         # Set a default radius (since it's not provided in input)
#         radius_km = 0.1

#         # Validate input
#         if not user_confirmation or not device_id or not address or not latitude or not longitude:
#             return {"status": "fail", "message": "Confirmation, device_id, address, latitude, and longitude are required."}, 400

#         # Transform the input data to the desired geofence format
#         geofence = {
#             "address": address,
#             "center": {
#                 "latitude": latitude,
#                 "longitude": longitude
#             },
#             "radius_km": radius_km  # default value for radius_km
#         }

#         if user_confirmation.lower() != "yes":
#             # Delete the geofence if user clicks "No"
#             update_result = device_collection.update_one(
#                 {"device.device_id": device_id},  # Find the device by device_id
#                 {"$pull": {"geofences": geofence}}  # Pull the entire geofence object from the geofences list
#             )
            
#             if update_result.modified_count == 0:
#                 # This will handle the case where no geofence was removed (geofence might not exist)
#                 return {"status": "fail", "message": f"No geofence found for address {address}."}, 404
            
#             return {
#                 "status": "success",
#                 "message": "Geofence removed successfully."
#             }, 200

#         # Add the geofence if user clicks "Yes"
#         update_result = device_collection.update_one(
#             {"device.device_id": device_id},
#             {"$push": {"geofences": geofence}}  # Push the geofence object into the geofences list
#         )

#         if update_result.modified_count == 0:
#             return {"status": "fail", "message": f"No device found with device_id {device_id}."}, 404

#         return {
#             "status": "success",
#             "message": "Static geofence added successfully."
#         }, 201 