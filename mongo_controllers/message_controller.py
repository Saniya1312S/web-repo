import os
from flask import request, jsonify, Response
from flask_restx import Namespace, Resource
from bson import json_util
from childcareconfig import child_db_instance, calculate_rolling_intervals
import joblib
from pendulum import now, parse, from_timestamp
# Load the model and vectorizer
model = joblib.load('mongo_controllers/spam_classifier.pkl')
vectorizer = joblib.load('mongo_controllers/tfidf_vectorizer.pkl')

# Initialize a Namespace for message-related API routes
message_namespace = Namespace("message", description="Message Management")

# device_type = "WEB"
collection_type = "message"
db_handle = child_db_instance.childcaredb_connection()

# Helper function to validate Unix timestamp in seconds (int)
def is_valid_unix_timestamp_seconds(timestamp):
    return isinstance(timestamp, int) and timestamp >= 0

# Helper function to validate Unix timestamp in milliseconds (int)
def is_valid_unix_timestamp_milliseconds(timestamp):
    return isinstance(timestamp, int) and timestamp >= 0

# Route for inserting a single message
@message_namespace.route('/single_message_insert')
class InsertSingleMessage(Resource):
    @message_namespace.doc(responses={
        201: 'Document inserted successfully.',
        400: 'Missing required fields in request.',
        500: 'Failed to insert data.'
    })
    def post(self):
        try:
            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            # Validate required fields
            if not all(k in data for k in ("device_id", "time", "sms_logs")):
                return {"message": "Missing required fields in request"}, 400

            # Validate `time` field (Unix timestamp in seconds)
            if not is_valid_unix_timestamp_seconds(data['time']):
                return {"message": "Invalid 'time' format. It must be a valid Unix timestamp in seconds."}, 400

            message_data = {
                "device_id": data['device_id'],
                "time": data['time'],  # Unix timestamp in seconds (as per input JSON)
                "sms_logs": []
            }

            # Validate and process each sms_log entry
            for log in data['sms_logs']:
                if not all(k in log for k in ("phone_number", "name", "messages")):
                    return {"message": "Invalid sms_log format, missing required fields"}, 400

                messages = []
                for message in log['messages']:
                    if not all(k in message for k in ("message", "message_time", "message_type")):
                        return {"message": "Invalid message format, missing required fields"}, 400

                    # Validate `message_time` field (Unix timestamp in milliseconds)
                    if not is_valid_unix_timestamp_milliseconds(message['message_time']):
                        return {"message": "Invalid 'message_time' format. It must be a valid Unix timestamp in milliseconds."}, 400

                    # Classify the message using the spam model
                    text = message.get('message', '')
                    if text:
                        message_tfidf = vectorizer.transform([text])
                        label = model.predict(message_tfidf)[0]
                        message['classification'] = 'spam' if label == 1 else 'ham'  # Add classification to message

                    messages.append(message)

                message_data['sms_logs'].append({
                    "phone_number": log['phone_number'],
                    "name": log['name'],
                    "messages": messages
                })

            # Insert the document into the database (use the 'message' collection)
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            inserted_id = child_db_instance.insert_one_document(collection_name, message_data)
            if inserted_id:
                return {"message": "Document inserted successfully", "inserted_id": str(inserted_id)}, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            return {"message": str(e)}, 500

# Route for inserting multiple messages
@message_namespace.route('/multiple_message_insert')
class InsertMultipleMessages(Resource):
    @message_namespace.doc(responses={
        201: 'Documents inserted successfully.',
        400: 'Missing required fields in one of the documents.',
        500: 'Failed to insert data.'
    })

    def post(self):
        try:
            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            if not isinstance(data, list):
                return {"message": "Data should be a list of documents"}, 400

            message_data_list = []
            for item in data:
                if not all(k in item for k in ("device_id", "time", "sms_logs")):
                    return {"message": "Missing required fields in one of the documents"}, 400

                # Validate `time` field (Unix timestamp in seconds)
                if not is_valid_unix_timestamp_seconds(item['time']):
                    return {"message": "Invalid 'time' format. It must be a valid Unix timestamp in seconds."}, 400

                message_data = {
                    "device_id": item['device_id'],
                    "time": item['time'],  # Unix timestamp in seconds (as per input JSON)
                    "sms_logs": []
                }

                for log in item['sms_logs']:
                    if not all(k in log for k in ("phone_number", "name", "messages")):
                        return {"message": "Invalid sms_log format, missing required fields"}, 400

                    messages = []
                    for message in log['messages']:
                        if not all(k in message for k in ("message", "message_time", "message_type")):
                            return {"message": "Invalid message format, missing required fields"}, 400

                        # Validate `message_time` field (Unix timestamp in milliseconds)
                        if not is_valid_unix_timestamp_milliseconds(message['message_time']):
                            return {"message": "Invalid 'message_time' format. It must be a valid Unix timestamp in milliseconds."}, 400

                        # Classify the message using the spam model
                        text = message.get('message', '')
                        if text:
                            message_tfidf = vectorizer.transform([text])
                            label = model.predict(message_tfidf)[0]
                            message['classification'] = 'spam' if label == 1 else 'ham'  # Add classification to message

                        messages.append(message)

                    message_data['sms_logs'].append({
                        "phone_number": log['phone_number'],
                        "name": log['name'],
                        "messages": messages
                    })

                message_data_list.append(message_data)

            # Insert the documents into the database (use the 'message' collection)
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            inserted_ids = child_db_instance.insert_multiple_documents(collection_name, message_data_list)
            if inserted_ids:
                return {
                    "message": "Documents inserted successfully",
                    "inserted_ids": [str(_id) for _id in inserted_ids]
                }, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            return {"message": str(e)}, 500

# Route for retrieving filtered message data using a static timestamp
@message_namespace.route('/get_messages_filter_data')
class MessageFilterData(Resource):
    @message_namespace.doc(responses={
        200: 'Returns filtered message data with message count.',
        400: 'device_id query parameter is required.',
        404: 'No matching data found using filter.',
        500: 'Error fetching message data.'
    })
    @message_namespace.param('device_id', 'Device ID to fetch message data for', type=str)
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

            # Unwind sms_logs to process individual log entries
            rolling_filter.append({"$unwind": "$sms_logs"})

            # Project only required fields and count the number of messages
            rolling_filter.append({
                "$project": {
                    "_id": 0,  # Exclude _id field
                    "phone_number": "$sms_logs.phone_number",
                    "name": "$sms_logs.name",
                    "message_count": {"$size": "$sms_logs.messages"},
                    "messages": "$sms_logs.messages"
                }
            })

            # Execute the aggregation pipeline
            result_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)
            result = list(result_cursor)

            if result:
                return Response(json_util.dumps(result), content_type="application/json", status=200)
            else:
                return {"message": "No matching data found using filter"}, 404

        except Exception as e:
            return {"message": str(e)}, 500


# Route for retrieving all messages
@message_namespace.route('/get_all_messages')
class GetAllMessages(Resource):
    @message_namespace.doc(responses={
        200: 'Returns all message data for the specified device_id.',
        400: 'device_id is required.',
        404: 'No message data found for the given device_id.'
    })
    @message_namespace.param('device_id', 'Device ID to fetch message data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        if not device_id:
            return {"message": "device_id is required"}, 400
        
        # Fetch the message data from the MongoDB collection
        collection_name = child_db_instance.device_db_collection(collection_type)[0]  # Assuming 'message' is the collection type
        try:
            data = child_db_instance.get_device_data(collection_name, device_id)
            if data:
                # Convert the MongoDB cursor to a list and then to JSON
                return Response(json_util.dumps(data), content_type='application/json')
            else:
                return {"message": "No message data found for the given device_id"}, 404
        except Exception as e:
            return {"message": f"Error fetching message data: {str(e)}"}, 500

def get_paginated_sms_logs(device_id, page, per_page, pagination_type):
    try:
        # Static timestamp for reference
        static_time = from_timestamp(1738367999)  # Example static 'end_time' for SMS logs
        
        # Fetch MongoDB_time_interval, set to 1 day if not available
        try:
            interval_days = float(os.getenv("MongoDB_time_interval", 1))
        except Exception as e:
            return {"message": "MongoDB_time_interval is not set or invalid"}, 500
        
        # Handle different pagination types: previous, current, or next
        if pagination_type == 'previous':
            start_time = static_time.subtract(days=interval_days * 2)
        elif pagination_type == 'next':
            start_time = static_time.add(days=interval_days * 2)
        else:
            start_time = static_time.subtract(days=interval_days)

        rolling_filter = calculate_rolling_intervals(device_id, start_time, interval_days)
        if not rolling_filter:
            return {"message": "Error creating filter"}, 500

        # Execute the aggregation pipeline (MongoDB query)
        collection_name = child_db_instance.device_db_collection(collection_type)[0]
        data_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)

        # Initialize list for SMS logs
        all_sms_logs = []
        
        for doc in data_cursor:
            if 'sms_logs' in doc:
                all_sms_logs.extend(doc['sms_logs'])  # Flatten the sms_logs arrays

        # Pagination logic
        total_count = len(all_sms_logs)
        total_pages = (total_count + per_page - 1) // per_page  # Total pages based on per_page
        start_index = (page - 1) * per_page
        end_index = start_index + per_page

        # Get the paginated SMS logs
        paginated_data = all_sms_logs[start_index:end_index]

        if paginated_data:
            response = {
                "data": json_util.dumps(paginated_data),  # Proper serialization of MongoDB data
                "total_count": total_count,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages
            }
            return Response(response['data'], content_type="application/json")
        else:
            # Return a 200 OK with a message if no data is found
            return {
                "message": f"No data found for the date {start_time.format('YYYY-MM-DD')}. Try checking for a different date."
            }, 200 
        
    except Exception as e:
        print(f"Error fetching paginated SMS logs: {str(e)}")
        return {"message": "Internal Server Error"}, 500
    
@message_namespace.route('/get_paginated_sms_logs')
class GetPaginatedSmsLogs(Resource):
    @message_namespace.doc(responses={
        200: 'Returns paginated SMS logs for the specified device_id',
        400: 'device_id or pagination parameters are required',
        404: 'No SMS logs found for the given device_id',
        500: 'Error fetching SMS logs'
    })
    @message_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @message_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @message_namespace.param('device_id', 'Device ID to fetch SMS logs for', type=str, default='5551231010')
    
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        page = request.args.get('page', 1, type=int)  # Default to page 1 if not provided
        per_page = request.args.get('per_page', 5, type=int)  # Default to 5 items per page if not provided

        if not device_id:
            return {"message": "device_id is required"}, 400
        
        # Call the helper function for SMS logs
        return get_paginated_sms_logs(device_id, page, per_page, 'current')


@message_namespace.route('/get_paginated_previous_sms_logs')
class GetPaginatedPreviousSmsLogs(Resource):
    @message_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @message_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @message_namespace.param('device_id', 'Device ID to fetch SMS logs for', type=str, default='5551231010')
    
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)

        if not device_id:
            return {"message": "device_id is required"}, 400
        return get_paginated_sms_logs(device_id, page, per_page, 'previous')


@message_namespace.route('/get_paginated_next_sms_logs')
class GetPaginatedNextSmsLogs(Resource):
    @message_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @message_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @message_namespace.param('device_id', 'Device ID to fetch SMS logs for', type=str, default='5551231010')
    
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)

        if not device_id:
            return {"message": "device_id is required"}, 400
        return get_paginated_sms_logs(device_id, page, per_page, 'next')
    
