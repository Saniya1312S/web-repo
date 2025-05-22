import os
from flask import request, jsonify, Response
from flask_restx import Namespace, Resource
from bson import json_util
from childcareconfig import child_db_instance, calculate_rolling_intervals
import redis
from pendulum import now, parse, from_timestamp

# Initialize a Namespace for browser-related API routes
browser_namespace = Namespace("browser", description="Browser Management")

# device_type = "WEB"
collection_type = "browser"
db_handle = child_db_instance.childcaredb_connection()


# Route for inserting a single browser history data document

@browser_namespace.route('/single_browser_insert')
class InsertSingleBrowserData(Resource):
    def post(self):
        try:
            data = request.get_json()
            
            if not data:
                return {"message": "No data provided"}, 400

            required_fields = ['device_id', 'time', 'browser_history_logs']
            if not all(field in data for field in required_fields):
                return {"message": "Missing required fields"}, 400

            browser_doc = {
                "device_id": str(data['device_id']),
                "time": data['time'],
                "browser_history_logs": []
            }

            for history in data['browser_history_logs']:
                required_history_fields = ['app', 'package_name', 'browse_history']
                if not all(field in history for field in required_history_fields):
                    return {"message": "Invalid browser history format"}, 400

                browser_doc['browser_history_logs'].append({
                    "app": history['app'],
                    "package_name": history['package_name'],
                    "browse_history": history['browse_history']
                })

            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            inserted_id = child_db_instance.insert_one_document(collection_name, browser_doc)
            
            if inserted_id:
                return {"message": "Document inserted successfully", "inserted_id": str(inserted_id)}, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            print(f"Error during insertion: {str(e)}")
            return {"message": f"Error during insertion: {str(e)}"}, 500

# Route for inserting multiple browser history data documents
@browser_namespace.route('/multiple_browser_insert')
class InsertMultipleBrowserData(Resource):
    def post(self):
        try:
            data = request.get_json()
            
            if not data:
                return {"message": "No data provided"}, 400

            if 'browser_data' not in data:
                return {"message": "Missing required field 'browser_data' in request"}, 400

            browser_data_list = data['browser_data']
            documents_to_insert = []

            for browser_data in browser_data_list:
                required_fields = ['device_id', 'time', 'browser_history_logs']
                if not all(field in browser_data for field in required_fields):
                    return {"message": "Missing required fields in a browser entry"}, 400

                browser_doc = {
                    "device_id": str(browser_data['device_id']),
                    "time": browser_data['time'],
                    "browser_history_logs": []
                }

                for history in browser_data['browser_history_logs']:
                    required_history_fields = ['app', 'package_name', 'browse_history']
                    if not all(field in history for field in required_history_fields):
                        return {"message": "Invalid browser history format"}, 400

                    browser_doc['browser_history_logs'].append({
                        "app": history['app'],
                        "package_name": history['package_name'],
                        "browse_history": history['browse_history']
                    })

                documents_to_insert.append(browser_doc)

            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            inserted_ids = child_db_instance.insert_multiple_documents(collection_name, documents_to_insert)
            
            if inserted_ids:
                return {"message": "Documents inserted successfully", "inserted_ids": [str(id) for id in inserted_ids]}, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            print(f"Error during insertion: {str(e)}")
            return {"message": f"Error during insertion: {str(e)}"}, 500

# Route for retrieving filtered browser history data
@browser_namespace.route('/get_filtered_browser_data')
class GetFilteredBrowserData(Resource):
    @browser_namespace.doc(responses={
        200: 'Returns filtered browser data (only browser_history_logs) with visit count',
        400: 'device_id query parameter is required',
        404: 'No matching data found using filter',
        500: 'Error creating filter'
    })
    @browser_namespace.param('device_id', 'Device ID to fetch browser data for', type=str)
    def get(self):
        device_id = request.args.get("device_id")
        if not device_id:
            return {"message": "device_id query parameter is required"}, 400

        static_time = parse("2025-01-31T18:30:00.000")

        try:
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            interval = float(child_db_instance.MongoDB_time_interval)
            rolling_filter = calculate_rolling_intervals(device_id, static_time, interval)
            
            if not rolling_filter:
                return {"message": "Error creating filter"}, 500

            rolling_filter.extend([
                {
                    "$unwind": "$browser_history_logs"
                },
                {
                    "$project": {
                        "_id": 0,
                        "app": "$browser_history_logs.app",
                        "package_name": "$browser_history_logs.package_name",
                        "browse_history": "$browser_history_logs.browse_history"
                    }
                }
            ])

            result_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)
            result = list(result_cursor)

            if result:
                return Response(json_util.dumps(result), content_type="application/json", status=200)
            else:
                return {"message": "No matching data found using filter"}, 404

        except Exception as e:
            return {"message": str(e)}, 500

# Route for retrieving all browser data
@browser_namespace.route('/get_all_browser_data')
class GetAllBrowserData(Resource):
    @browser_namespace.doc(responses={
        200: 'Returns all browser data for the specified device_id.',
        400: 'device_id is required.',
        404: 'No browser data found for the given device_id.'
    })
    @browser_namespace.param('device_id', 'Device ID to fetch browser data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        if not device_id:
            return {"message": "device_id is required"}, 400
        
        # Fetch the browser data from the MongoDB collection
        collection_name, _ = child_db_instance.device_db_collection(collection_type)
        data = child_db_instance.get_device_data(collection_name, device_id)
        if data:
            return Response(json_util.dumps(data), content_type='application/json')
        else:
            return {"message": "No browser data found for the given device_id"}, 404
        

# Helper function for paginated browser history logs
def get_paginated_browser_history_logs(device_id, page, per_page, pagination_type):
    try:
        static_time = from_timestamp(1738367999)
        interval_days = float(os.getenv("MongoDB_time_interval", 1))

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

        all_browser_history_logs = []
        
        for doc in data_cursor:
            if 'browser_history_logs' in doc:
                all_browser_history_logs.extend(doc['browser_history_logs'])

        total_count = len(all_browser_history_logs)
        total_pages = (total_count + per_page - 1) // per_page
        start_index = (page - 1) * per_page
        end_index = start_index + per_page

        paginated_data = all_browser_history_logs[start_index:end_index]

        if paginated_data:
            response = {
                "data": json_util.dumps(paginated_data),
                "total_count": total_count,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages
            }
            return Response(response['data'], content_type="application/json")
        else:
            return {
                "message": f"No data found for the date {start_time.strftime('%Y-%m-%d')}. Try checking for a different date."
            }, 200 
    except Exception as e:
        print(f"Error fetching paginated browser history logs: {str(e)}")
        return {"message": "Internal Server Error"}, 500
    
# API Endpoints for current, previous, and next pagination for browser history logs
@browser_namespace.route('/get_paginated_browser_history_logs')
class GetPaginatedCurrentBrowserHistoryLogs(Resource):
    @browser_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @browser_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @browser_namespace.param('device_id', 'Device ID to fetch browser history logs for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        page = request.args.get('page', 1, type=int)  # Default to page 1 if not provided
        per_page = request.args.get('per_page', 5, type=int)  # Default to 5 items per page if not provided
        
        if not device_id:
            return {"message": "device_id is required"}, 400
        return get_paginated_browser_history_logs(device_id, page, per_page, 'current')


@browser_namespace.route('/get_paginated_previous_browser_history_logs')
class GetPaginatedPreviousBrowserHistoryLogs(Resource):
    @browser_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @browser_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @browser_namespace.param('device_id', 'Device ID to fetch browser history logs for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        page = request.args.get('page', 1, type=int)  # Default to page 1 if not provided
        per_page = request.args.get('per_page', 5, type=int)  # Default to 5 items per page if not provided
        
        if not device_id:
            return {"message": "device_id is required"}, 400
        return get_paginated_browser_history_logs(device_id, page, per_page, 'previous')


@browser_namespace.route('/get_paginated_next_browser_history_logs')
class GetPaginatedNextBrowserHistoryLogs(Resource):
    @browser_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @browser_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @browser_namespace.param('device_id', 'Device ID to fetch browser history logs for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        page = request.args.get('page', 1, type=int)  # Default to page 1 if not provided
        per_page = request.args.get('per_page', 5, type=int)  # Default to 5 items per page if not provided
        
        if not device_id:
            return {"message": "device_id is required"}, 400
        return get_paginated_browser_history_logs(device_id, page, per_page, 'next')
