from flask import request, Response
from flask_restx import Namespace, Resource
from bson import json_util
from pendulum import parse
from childcareconfig import child_db_instance, calculate_rolling_intervals
from dotenv import load_dotenv
import json
from pendulum import now, parse, from_timestamp
import logging
load_dotenv()

# Initialize a Namespace for social media-related API routes
social_media_namespace = Namespace("social_media", description="Social Media Call and Message Logs")

# Define collection type
collection_type = "social_media"
db_handle = child_db_instance.childcaredb_connection()

# Route for inserting social media data (calls and messages)
@social_media_namespace.route('/insert_social_media_data')
class InsertSocialMediaData(Resource):
    @social_media_namespace.doc(responses={201: 'Document inserted successfully', 400: 'Invalid input data', 500: 'Insertion failed'})
    def post(self):
        try:
            # Step 1: Get the JSON data from the request
            data = request.get_json()

            # Step 2: Validate that the data is not empty
            if not data:
                return {"message": "No data provided"}, 400

            # Step 3: Validate required fields in the social media document
            missing_fields = [k for k in ["device_id", "time", "social_media_log"] if k not in data]
            if missing_fields:
                return {"message": f"Missing required fields: {', '.join(missing_fields)}"}, 400

            # Prepare the social media data for insertion
            social_media_data = {
                "device_id": data['device_id'],
                "time": data['time'],
                "social_media_log": []
            }

            # Step 4: Validate and process each social media entry in the 'social_media_log'
            for social_media in data['social_media_log']:
                missing_fields = [k for k in ["appname", "packagename", "call_log", "message_log"] if k not in social_media]
                if missing_fields:
                    return {"message": f"Invalid social_media format, missing fields: {', '.join(missing_fields)}"}, 400

                # Validate each call log based on the app type (WhatsApp, Telegram, etc.)
                for call in social_media['call_log']:
                    if social_media["appname"] in ["WhatsApp", "Telegram"]:
                        # WhatsApp and Telegram use phone_number and name
                        missing_fields = [k for k in ["phone_number", "name", "call_type", "call_mode", "call_time", "duration"] if k not in call]
                    else:
                        # Other apps like Snapchat, Instagram, Facebook, Twitter use user_id
                        missing_fields = [k for k in ["user_id", "call_type", "call_mode", "call_time", "duration"] if k not in call]

                    if missing_fields:
                        return {"message": f"Invalid call log format, missing fields: {', '.join(missing_fields)}"}, 400

                # Validate the message log (adjusting based on app type)
                for message in social_media['message_log']:
                    if social_media["appname"] in ["WhatsApp", "Telegram"]:
                        # WhatsApp and Telegram use phone_number and name in the message_log
                        missing_fields = [k for k in ["phone_number", "name", "message_detail"] if k not in message]
                    else:
                        # Other apps use user_id in the message_log
                        missing_fields = [k for k in ["user_id", "message_detail"] if k not in message]

                    if missing_fields:
                        return {"message": f"Invalid message log format, missing fields: {', '.join(missing_fields)}"}, 400

                    # Validate each message detail
                    for detail in message['message_detail']:
                        missing_fields = [k for k in ["message", "message_type", "message_time", "classification"] if k not in detail]
                        if missing_fields:
                            return {"message": f"Invalid message detail format, missing fields: {', '.join(missing_fields)}"}, 400

                # Validate contacts (optional, only for certain apps like Snapchat, Instagram, Facebook, etc.)
                if "contacts" in social_media:
                    if social_media["appname"] == "Snapchat":
                        # Snapchat specific contact fields
                        for contact in social_media["contacts"]:
                            missing_fields = [k for k in ["user_id", "contact_name", "contact_snap"] if k not in contact]
                            if missing_fields:
                                return {"message": f"Invalid contact format for Snapchat, missing fields: {', '.join(missing_fields)}"}, 400
                    elif social_media["appname"] == "Instagram":
                        # Instagram specific contact fields
                        for contact in social_media["contacts"].get("followers", []):
                            missing_fields = [k for k in ["user_id", "user_name", "full_name"] if k not in contact]
                            if missing_fields:
                                return {"message": f"Invalid contact format for Instagram followers, missing fields: {', '.join(missing_fields)}"}, 400
                        for contact in social_media["contacts"].get("following", []):
                            missing_fields = [k for k in ["user_id", "user_name", "full_name"] if k not in contact]
                            if missing_fields:
                                return {"message": f"Invalid contact format for Instagram following, missing fields: {', '.join(missing_fields)}"}, 400
                    elif social_media["appname"] in ["Facebook", "Twitter"]:
                        # Facebook and Twitter specific contact fields
                        for contact in social_media["contacts"]:
                            missing_fields = [k for k in ["user_id", "user_name"] if k not in contact]
                            if missing_fields:
                                return {"message": f"Invalid contact format for {social_media['appname']}, missing fields: {', '.join(missing_fields)}"}, 400

                # Add the validated social media log entry to the document
                social_media_data['social_media_log'].append(social_media)

            # Step 5: Insert the document into the database
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            inserted_id = child_db_instance.insert_one_document(collection_name, social_media_data)

            if inserted_id:
                return {
                    "message": "Document inserted successfully",
                    "inserted_id": str(inserted_id)
                }, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            # Catch any exception and return an error message
            return {"message": str(e)}, 500


# Route for inserting multiple social media data documents
@social_media_namespace.route('/multiple_social_media_data_insert')
class InsertMultipleSocialMediaData(Resource):
    @social_media_namespace.doc(responses={201: 'Documents inserted successfully', 400: 'Invalid input data', 500: 'Insertion failed'})
    def post(self):
        try:
            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            if not isinstance(data, list):
                return {"message": "Data should be a list of documents"}, 400

            social_media_data_list = []
            for item in data:
                # Validate required fields in the social media document
                missing_fields = [k for k in ["device_id", "time", "social_media_log"] if k not in item]
                if missing_fields:
                    return {"message": f"Missing required fields: {', '.join(missing_fields)}"}, 400

                social_media_data = {
                    "device_id": item['device_id'],
                    "time": item['time'],
                    "social_media_log": []
                }

                # Validate and process each social media entry
                for social_media in item['social_media_log']:
                    missing_fields = [k for k in ["appname", "packagename", "call_log", "message_log"] if k not in social_media]
                    if missing_fields:
                        return {"message": f"Invalid social_media format, missing fields: {', '.join(missing_fields)}"}, 400
                    
                    # Validate call log
                    for call in social_media['call_log']:
                        if social_media["appname"] in ["WhatsApp", "Telegram"]:
                            # WhatsApp and Telegram use phone_number and name
                            missing_fields = [k for k in ["phone_number", "name", "call_type", "call_mode", "call_time", "duration"] if k not in call]
                        else:
                            # Snapchat, Instagram, Facebook, Twitter use user_id
                            missing_fields = [k for k in ["user_id", "call_type", "call_mode", "call_time", "duration"] if k not in call]
                        
                        if missing_fields:
                            return {"message": f"Invalid call log format, missing fields: {', '.join(missing_fields)}"}, 400

                    # Validate message log (adjusting based on app type)
                    for message in social_media['message_log']:
                        if social_media["appname"] in ["WhatsApp", "Telegram"]:
                            # WhatsApp and Telegram use phone_number and name in the message_log
                            missing_fields = [k for k in ["phone_number", "name", "message_detail"] if k not in message]
                        else:
                            # Snapchat, Instagram, Facebook, Twitter use user_id in the message_log
                            missing_fields = [k for k in ["user_id", "message_detail"] if k not in message]
                        
                        if missing_fields:
                            return {"message": f"Invalid message log format, missing fields: {', '.join(missing_fields)}"}, 400
                        
                        # Validate message detail
                        for detail in message['message_detail']:
                            missing_fields = [k for k in ["message", "message_type", "message_time", "classification"] if k not in detail]
                            if missing_fields:
                                return {"message": f"Invalid message detail format, missing fields: {', '.join(missing_fields)}"}, 400
                    
                    # Validate contacts (optional, only for certain apps)
                    if "contacts" in social_media:
                        if social_media["appname"] == "Snapchat":
                            # Snapchat specific contact fields
                            for contact in social_media["contacts"]:
                                missing_fields = [k for k in ["user_id", "contact_name", "contact_snap"] if k not in contact]
                                if missing_fields:
                                    return {"message": f"Invalid contact format for Snapchat, missing fields: {', '.join(missing_fields)}"}, 400
                        elif social_media["appname"] == "Instagram":
                            # Instagram specific contact fields
                            for contact in social_media["contacts"].get("followers", []):
                                missing_fields = [k for k in ["user_id", "user_name", "full_name"] if k not in contact]
                                if missing_fields:
                                    return {"message": f"Invalid contact format for Instagram followers, missing fields: {', '.join(missing_fields)}"}, 400
                            for contact in social_media["contacts"].get("following", []):
                                missing_fields = [k for k in ["user_id", "user_name", "full_name"] if k not in contact]
                                if missing_fields:
                                    return {"message": f"Invalid contact format for Instagram following, missing fields: {', '.join(missing_fields)}"}, 400
                        elif social_media["appname"] in ["Facebook", "Twitter"]:
                            # Facebook and Twitter specific contact fields
                            for contact in social_media["contacts"]:
                                missing_fields = [k for k in ["user_id", "user_name"] if k not in contact]
                                if missing_fields:
                                    return {"message": f"Invalid contact format for {social_media['appname']}, missing fields: {', '.join(missing_fields)}"}, 400

                    social_media_data['social_media_log'].append(social_media)

                social_media_data_list.append(social_media_data)

            # Insert the documents into the database (use the 'social_media' collection)
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            inserted_ids = child_db_instance.insert_multiple_documents(collection_name, social_media_data_list)
            if inserted_ids:
                return {
                    "message": "Documents inserted successfully",
                    "inserted_ids": [str(_id) for _id in inserted_ids]
                }, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            return {"message": str(e)}, 500
        
@social_media_namespace.route('/get_filtered_social_media_data')
class GetFilteredSocialMediaData(Resource):
    @social_media_namespace.doc(responses={
        200: 'Returns filtered social media data (calls, messages, contacts).',
        400: 'device_id, appname, or log_type query parameters are required.',
        404: 'No matching data found using filter.',
        500: 'Error fetching social media data.'
    })
    @social_media_namespace.param('device_id', 'Device ID to fetch social media data for', type=str, required=True)
    @social_media_namespace.param('appname', 'The appname to filter the logs', type=str, required=True)
    @social_media_namespace.param('log_type', 'Type of log to fetch (calls, messages, contacts)', type=str, enum=['calls', 'messages', 'contacts'], default='calls')
    def get(self):
        device_id = request.args.get('device_id')
        appname = request.args.get('appname')
        log_type = request.args.get('log_type', 'calls')
        
        if not device_id or not appname:
            return {"message": "device_id and appname are required"}, 400
        
        try:
            # Use the specific static timestamp
            static_time = from_timestamp(1738367999)
            interval = float(child_db_instance.MongoDB_time_interval)
            
            # Calculate start time by subtracting interval days
            start_time = static_time.subtract(days=interval)
            
            rolling_filter = calculate_rolling_intervals(device_id, start_time, interval)
            
            if not rolling_filter:
                return {"message": "Error creating filter"}, 500
            
            collection_name = child_db_instance.device_db_collection(collection_type)[0]
            data_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)
            
            all_calls = []
            all_messages = []
            all_contacts = []
            
            for doc in data_cursor:
                if 'social_media_log' in doc:
                    app_data = next((app for app in doc['social_media_log'] if app['appname'] == appname), None)
                    if app_data:
                        if log_type == 'calls' and 'call_log' in app_data:
                            all_calls.extend(app_data['call_log'])
                        elif log_type == 'messages' and 'message_log' in app_data:
                            all_messages.extend(app_data['message_log'])
                        elif log_type == 'contacts':
                            if appname == "Instagram":
                                if 'contacts' in app_data:
                                    all_contacts.append({
                                        "followers": app_data['contacts'].get('followers', []),
                                        "following": app_data['contacts'].get('following', [])
                                    })
                            else:
                                if 'contacts' in app_data:
                                    all_contacts.extend(app_data['contacts'])
            
            if log_type == 'calls':
                paginated_data = all_calls
            elif log_type == 'messages':
                paginated_data = all_messages
            else:
                paginated_data = all_contacts
            
            if not paginated_data:
                return {"message": "No matching data found for the given filter."}, 404
            
            if appname == "Instagram" and log_type == 'contacts':
                return Response(json_util.dumps({
                    "followers": all_contacts[0].get("followers", []),
                    "following": all_contacts[0].get("following", [])
                }), content_type='application/json')
            else:
                return Response(json_util.dumps(paginated_data), content_type='application/json')
            
        except Exception as e:
            logging.error(f"Error fetching filtered social media data: {str(e)}")
            return {"message": f"Error fetching filtered social media data: {str(e)}"}, 500
        
# Route for retrieving all social media data
@social_media_namespace.route('/get_all_social_media_data')
class GetAllSocialMediaData(Resource):
    @social_media_namespace.doc(responses={
        200: 'Returns all social media data for the specified device_id.',
        400: 'device_id is required.',
        404: 'No social media data found for the given device_id.'
    })
    @social_media_namespace.param('device_id', 'Device ID to fetch social media data for', type=str, default=5551231010)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        if not device_id:
            return {"message": "device_id is required"}, 400
        
        # Fetch the social media data from the MongoDB collection
        collection_name, _ = child_db_instance.device_db_collection(collection_type)
        data = child_db_instance.get_device_data(collection_name, device_id)
        if data:
            return Response(json_util.dumps(data), content_type='application/json')
        else:
            return {"message": "No social media data found for the given device_id"}, 404

def get_social_media_data(device_id, appname, page, per_page, pagination_type, interval_days=1, log_type='calls'):
    try:
        static_time = from_timestamp(1738367999)
        
        if pagination_type == 'previous':
            start_time = static_time.subtract(days=interval_days * 2)
        elif pagination_type == 'next':
            start_time = static_time.add(days=interval_days * 2)
        else:
            start_time = static_time.subtract(days=interval_days)

        rolling_filter = calculate_rolling_intervals(device_id, start_time, interval_days)
        if not rolling_filter:
            return {"message": "Error creating filter"}, 500

        collection_name = child_db_instance.device_db_collection(collection_type)[0]
        data_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)

        all_calls = []
        all_messages = []
        all_contacts = []
        instagram_contacts = {
            "followers": [],
            "following": []
        }

        for doc in data_cursor:
            if 'social_media_log' in doc:
                app_data = next((app for app in doc['social_media_log'] if app['appname'] == appname), None)
                if app_data:
                    if log_type == 'calls' and 'call_log' in app_data:
                        all_calls.extend(app_data['call_log'])
                    elif log_type == 'messages' and 'message_log' in app_data:
                        all_messages.extend(app_data['message_log'])
                    elif log_type == 'contacts':
                        if appname == "Instagram":
                            if 'contacts' in app_data:
                                if 'followers' in app_data['contacts']:
                                    instagram_contacts["followers"].extend(app_data['contacts']['followers'])
                                if 'following' in app_data['contacts']:
                                    instagram_contacts["following"].extend(app_data['contacts']['following'])
                        else:
                            if 'contacts' in app_data:
                                all_contacts.extend(app_data['contacts'])

        if log_type == 'calls':
            paginated_data = all_calls
        elif log_type == 'messages':
            paginated_data = all_messages
        elif log_type == 'contacts':
            if appname == "Instagram":
                paginated_data = {
                    "followers": instagram_contacts["followers"],
                    "following": instagram_contacts["following"]
                }
            else:
                paginated_data = all_contacts

        if not paginated_data:
            return {
                "message": f"No data found for app '{appname}' on device '{device_id}' for the requested log type '{log_type}'."
            }, 200

        # Apply pagination only if it's not Instagram contacts
        if log_type != 'contacts' or appname != "Instagram":
            start_index = (page - 1) * per_page
            end_index = start_index + per_page
            paginated_data = paginated_data[start_index:end_index]

        return paginated_data
    except Exception as e:
        print(f"Error fetching social media data: {str(e)}")
        return {"message": "Internal Server Error"}, 500


@social_media_namespace.route('/get_paginated_social_media_data')
class GetPaginatedSocialMediaData(Resource):
    @social_media_namespace.doc(responses={200: 'Returns paginated logs for the specified device_id and appname', 400: 'device_id, appname, or pagination parameters are required', 500: 'Error fetching logs'})
    @social_media_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @social_media_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @social_media_namespace.param('device_id', 'Device ID to fetch logs for', type=str, default='5551231010')
    @social_media_namespace.param('appname', 'Name of the app to filter logs', type=str)
    @social_media_namespace.param('log_type', 'Type of log to fetch (calls, messages, contacts)', type=str, enum=['calls', 'messages', 'contacts'], default='calls')
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        appname = request.args.get('appname')  # Retrieve appname from query parameters
        page = request.args.get('page', 1, type=int)  # Default to page 1 if not provided
        per_page = request.args.get('per_page', 5, type=int)  # Default to 5 items per page if not provided
        log_type = request.args.get('log_type', 'calls', type=str)  # Default to 'calls' if not provided

        if not device_id or not appname:
            return {"message": "device_id and appname are required"}, 400
        
        # Call the generalized method with 'current' pagination type and log_type filter
        response = get_social_media_data(device_id, appname, page, per_page, 'current', log_type=log_type)
        
        # Return the direct response, no need for wrapping in JSON
        return Response(json_util.dumps(response), content_type="application/json")


@social_media_namespace.route('/get_paginated_previous_social_media_data')
class GetPaginatedPreviousSocialMediaData(Resource):
    @social_media_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @social_media_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @social_media_namespace.param('device_id', 'Device ID to fetch logs for', type=str, default='5551231010')
    @social_media_namespace.param('appname', 'Name of the app to filter logs', type=str)
    @social_media_namespace.param('log_type', 'Type of log to fetch (calls, messages, contacts)', type=str, enum=['calls', 'messages', 'contacts'], default='calls')
    def get(self):
        device_id = request.args.get('device_id')
        appname = request.args.get('appname')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        log_type = request.args.get('log_type', 'calls', type=str)

        if not device_id or not appname:
            return {"message": "device_id and appname are required"}, 400
        
        # Call the generalized method with 'previous' pagination type and log_type filter
        response = get_social_media_data(device_id, appname, page, per_page, 'previous', log_type=log_type)
        
        # Return the direct response, no need for wrapping in JSON
        return Response(json_util.dumps(response), content_type="application/json")

@social_media_namespace.route('/get_paginated_next_social_media_data')
class GetPaginatedNextSocialMediaData(Resource):
    @social_media_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @social_media_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @social_media_namespace.param('device_id', 'Device ID to fetch logs for', type=str, default='5551231010')
    @social_media_namespace.param('appname', 'Name of the app to filter logs', type=str)
    @social_media_namespace.param('log_type', 'Type of log to fetch (calls, messages, contacts)', type=str, enum=['calls', 'messages', 'contacts'], default='calls')
    def get(self):
        device_id = request.args.get('device_id')
        appname = request.args.get('appname')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        log_type = request.args.get('log_type', 'calls', type=str)

        if not device_id or not appname:
            return {"message": "device_id and appname are required"}, 400
        
        # Call the generalized method with 'next' pagination type and log_type filter
        response = get_social_media_data(device_id, appname, page, per_page, 'next', log_type=log_type)
        
        # Return the direct response, no need for wrapping in JSON
        return Response(json_util.dumps(response), content_type="application/json")





