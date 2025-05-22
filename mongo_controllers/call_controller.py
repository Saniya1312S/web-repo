# mongo_controllers/call_controller.py
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
call_namespace = Namespace("call", description="Call Management")

# device_type = "WEB"
collection_type="call"
db_handle = child_db_instance.childcaredb_connection()

# Route for inserting a single call data document
@call_namespace.route('/single_call_insert')
class InsertSingleCallData(Resource):
    @call_namespace.doc(responses={
        201: 'Document inserted successfully',
        400: 'Invalid input data',
        500: 'Insertion failed'
    })
    def post(self):
        try:
            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            # Validate required fields: device_id, time, call_logs
            if not all(k in data for k in ("device_id", "time", "call_logs")):
                return {"message": "Missing required fields in request"}, 400

            call_data = {
                "device_id": data['device_id'],
                "time": data['time'],
                "call_logs": []
            }

            # Validate and process each call_log entry
            for call_log in data['call_logs']:
                if not all(k in call_log for k in ("phone_number", "name", "call_details")):
                    return {"message": "Invalid call_log format, missing required fields"}, 400

                # Validate that each call_detail contains the required keys
                for detail in call_log['call_details']:
                    if not all(k in detail for k in ("call_types", "call_time", "duration")):
                        return {"message": "Invalid call_details format, missing required fields"}, 400

                call_data['call_logs'].append({
                    "phone_number": call_log['phone_number'],
                    "name": call_log['name'],
                    "call_details": call_log['call_details']  # Keep as an array
                })

            # Insert the document into the database (use the 'call' collection)
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            inserted_id = child_db_instance.insert_one_document(collection_name, call_data)
            if inserted_id:
                return {"message": "Document inserted successfully", "inserted_id": str(inserted_id)}, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            return {"message": str(e)}, 500

# Route for inserting multiple call data documents
@call_namespace.route('/multiple_call_insert')
class InsertMultipleCallData(Resource):
    @call_namespace.doc(responses={
        201: 'Documents inserted successfully',
        400: 'Invalid input data',
        500: 'Insertion failed'
    })
    def post(self):
        try:
            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            if not isinstance(data, list):
                return {"message": "Data should be a list of documents"}, 400

            call_data_list = []
            for item in data:
                # Validate required fields for each document
                if not all(k in item for k in ("device_id", "time", "call_logs")):
                    return {"message": "Missing required fields in one of the documents"}, 400

                # Validate each call_log in the document
                for call_log in item['call_logs']:
                    if not all(k in call_log for k in ("phone_number", "name", "call_details")):
                        return {"message": "Invalid call_log format, missing required fields"}, 400
                    for detail in call_log['call_details']:
                        if not all(k in detail for k in ("call_types", "call_time", "duration")):
                            return {"message": "Invalid call_details format, missing required fields"}, 400

                call_data = {
                    "device_id": item['device_id'],
                    "time": item['time'],
                    "call_logs": []
                }

                for call_log in item['call_logs']:
                    call_data['call_logs'].append({
                        "phone_number": call_log['phone_number'],
                        "name": call_log['name'],
                        "call_details": call_log['call_details']
                    })

                call_data_list.append(call_data)

            # Insert the documents into the database (use the 'call' collection)
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            inserted_ids = child_db_instance.insert_multiple_documents(collection_name, call_data_list)
            if inserted_ids:
                return {
                    "message": "Documents inserted successfully",
                    "inserted_ids": [str(_id) for _id in inserted_ids]
                }, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            return {"message": str(e)}, 500

@call_namespace.route('/get_call_filter_data')
class GetCallFilterData(Resource):
    @call_namespace.doc(responses={
        200: 'Returns filtered call data (only call_logs) with call count',
        400: 'device_id query parameter is required',
        404: 'No matching data found using filter',
        500: 'Error creating filter'
    })
    @call_namespace.param('device_id', 'Device ID to fetch call data for', type=str)
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
            # Call the calculate_rolling_intervals function with the static time
            rolling_filter = calculate_rolling_intervals(device_id, static_time, interval)
            if not rolling_filter:
                return {"message": "Error creating filter"}, 500

            # Modify the pipeline to project only the `call_logs` field and count call_details
            rolling_filter.append({
                "$unwind": "$call_logs"  # Unwind the call_logs array to get individual call log objects
            })

            rolling_filter.append({
                "$project": {
                    "_id": 0,  # Exclude the _id field
                    "phone_number": "$call_logs.phone_number",  # Extract phone_number from call_logs
                    "name": "$call_logs.name",  # Extract name from call_logs
                    "call_details": "$call_logs.call_details",  # Extract call_details from call_logs
                    "count": {"$size": "$call_logs.call_details"}  # Count number of call details
                }
            })

            # Execute the aggregation pipeline using aggregate()
            result_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)
            result = list(result_cursor)

            if result:
                return Response(json_util.dumps(result), content_type="application/json", status=200)
            else:
                return {"message": "No matching data found using filter"}, 404

        except Exception as e:
            return {"message": str(e)}, 500



# Define an API endpoint to fetch call-related data
@call_namespace.route('/get_call_data')
class GetCallData(Resource):
    @call_namespace.doc(responses={
        200: 'Returns call data for the specified device_id',
        400: 'device_id is required',
        404: 'No call data found for the given device_id',
        500: 'Error fetching call data'
    })
    @call_namespace.param('device_id', 'Device ID to fetch call  data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        if not device_id:
            return {"message": "device_id is required"}, 400
        
        # Fetch the call data from the MongoDB collection
        collection_name = child_db_instance.device_db_collection(collection_type)[0]  # Assuming 'call' is the collection type
        try:
            data = child_db_instance.get_device_data(collection_name, device_id)
            if data:
                # Convert the MongoDB cursor to a list and then to JSON
                return Response(json_util.dumps(data), content_type='application/json')
            else:
                return {"message": "No call data found for the given device_id"}, 404
        except Exception as e:
            return {"message": f"Error fetching call data: {str(e)}"}, 500

@call_namespace.route('/get_call_summary')
class GetCallSummary(Resource):
    @call_namespace.doc(responses={
        200: 'Returns total counts of incoming, outgoing, and missed calls',
        400: 'device_id query parameter is required',
        404: 'No matching data found using filter',
        500: 'Error fetching call summary'
    })
    @call_namespace.param('device_id', 'Device ID to fetch call summary for', type=str)
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

            # Unwind call_logs to get each call record
            rolling_filter.append({"$unwind": "$call_logs"})
            rolling_filter.append({"$unwind": "$call_logs.call_details"})  # Unwind nested call details

            # Group by call type and count occurrences
            rolling_filter.append({
                "$group": {
                    "_id": "$call_logs.call_details.call_types",  # Group by call type
                    "count": {"$sum": 1}  # Count occurrences of each call type
                }
            })

            # Project final result into structured format
            rolling_filter.append({
                "$project": {
                    "_id": 0,
                    "call_type": "$_id",
                    "count": 1
                }
            })

            # Execute the aggregation pipeline
            result_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)
            result_list = list(result_cursor)

            # Convert results into structured response
            call_summary = {
                "incoming_calls": 0,
                "outgoing_calls": 0,
                "missed_calls": 0
            }

            for record in result_list:
                call_type = record["call_type"].lower()  # Normalize case
                if call_type == "incoming":
                    call_summary["incoming_calls"] = record["count"]
                elif call_type == "outgoing":
                    call_summary["outgoing_calls"] = record["count"]
                elif call_type == "missed":
                    call_summary["missed_calls"] = record["count"]

            return Response(json_util.dumps(call_summary), content_type="application/json", status=200)

        except Exception as e:
            return {"message": str(e)}, 500

# Helper function for paginated data, customized for Call Logs
def get_paginated_call_logs(device_id, page, per_page, pagination_type):
    try:
        # Static timestamp for reference
        static_time = from_timestamp(1738367999)  # Example static 'end_time' for call logs
        
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
            # For current pagination, just use the calculated start_time
            start_time = static_time.subtract(days=interval_days)

                # Build your aggregation query with the start_time
        rolling_filter = calculate_rolling_intervals(device_id, start_time, interval_days)
        if not rolling_filter:
            return {"message": "Error creating filter"}, 500

        # Execute the aggregation pipeline (MongoDB query)
        collection_name = child_db_instance.device_db_collection(collection_type)[0]
        data_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)

        # Initialize list for call logs
        all_call_logs = []
        
        for doc in data_cursor:
            if 'call_logs' in doc:
                all_call_logs.extend(doc['call_logs'])  # Flatten the call_logs arrays

        # Pagination logic
        total_count = len(all_call_logs)
        total_pages = (total_count + per_page - 1) // per_page  # Total pages based on per_page
        start_index = (page - 1) * per_page
        end_index = start_index + per_page

        # Get the paginated call logs
        paginated_data = all_call_logs[start_index:end_index]

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
        print(f"Error fetching paginated call logs: {str(e)}")
        return {"message": "Internal Server Error"}, 500


# API Endpoints for current, previous, and next pagination for call logs

@call_namespace.route('/get_paginated_call_logs')
class GetPaginatedCurrentCallLogs(Resource):
    @call_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @call_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @call_namespace.param('device_id', 'Device ID to fetch call logs for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        page = request.args.get('page', 1, type=int)  # Default to page 1 if not provided
        per_page = request.args.get('per_page', 5, type=int)  # Default to 5 items per page if not provided
        
        if not device_id:
            return {"message": "device_id is required"}, 400
        return get_paginated_call_logs(device_id, page, per_page, 'current')


@call_namespace.route('/get_paginated_previous_call_logs')
class GetPaginatedPreviousCallLogs(Resource):
    @call_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @call_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @call_namespace.param('device_id', 'Device ID to fetch call logs for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        page = request.args.get('page', 1, type=int)  # Default to page 1 if not provided
        per_page = request.args.get('per_page', 5, type=int)  # Default to 5 items per page if not provided
        
        if not device_id:
            return {"message": "device_id is required"}, 400
        return get_paginated_call_logs(device_id, page, per_page, 'previous')


@call_namespace.route('/get_paginated_next_call_logs')
class GetPaginatedNextCallLogs(Resource):
    @call_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @call_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @call_namespace.param('device_id', 'Device ID to fetch call logs for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        page = request.args.get('page', 1, type=int)  # Default to page 1 if not provided
        per_page = request.args.get('per_page', 5, type=int)  # Default to 5 items per page if not provided
        
        if not device_id:
            return {"message": "device_id is required"}, 400
        return get_paginated_call_logs(device_id, page, per_page, 'next')


