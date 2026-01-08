"""
AI Shopping Assistant REST API with Authentication
Endpoints: Login, Health, Products, Cart, Chat
"""

import json
import oci
import time
import requests
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from functools import wraps
from collections import defaultdict


# ------------------------------------------------------------
# Config Loader
# ------------------------------------------------------------
class ConfigLoader:
    def __init__(self, config_path="config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self):
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")

    def get(self, *keys):
        value = self.config
        for key in keys:
            value = value[key]
        return value


# ------------------------------------------------------------
# Rate Limiter
# ------------------------------------------------------------
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
        self.limits = {
            'user': {'max_requests': 10, 'window': 60},
            'admin': {'max_requests': 50, 'window': 60}
        }
    
    def is_allowed(self, user_id, role):
        current_time = time.time()
        limit_config = self.limits.get(role, self.limits['user'])
        
        # Clean old requests
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if current_time - req_time < limit_config['window']
        ]
        
        # Check limit
        if len(self.requests[user_id]) >= limit_config['max_requests']:
            return False, limit_config
        
        # Add new request
        self.requests[user_id].append(current_time)
        return True, limit_config


# ------------------------------------------------------------
# Authentication Middleware
# ------------------------------------------------------------
rate_limiter = RateLimiter()

def require_auth(f):
    """Decorator to require authentication headers"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check required headers
        user_id = request.headers.get('X-User-ID')
        user_role = request.headers.get('X-User-Role')
        user_name = request.headers.get('X-User-Name')
        
        if not all([user_id, user_role, user_name]):
            return jsonify({
                "success": False,
                "error": "Missing required authentication headers",
                "required_headers": ["X-User-ID", "X-User-Role", "X-User-Name"],
                "status_code": 401
            }), 401
        
        # Validate role
        if user_role not in ['user', 'admin']:
            return jsonify({
                "success": False,
                "error": "Invalid role. Must be 'user' or 'admin'",
                "provided_role": user_role,
                "valid_roles": ["user", "admin"],
                "status_code": 400
            }), 400
        
        # Check rate limit
        allowed, limit_config = rate_limiter.is_allowed(user_id, user_role)
        if not allowed:
            retry_after = limit_config['window']
            return jsonify({
                "success": False,
                "error": f"Rate limit exceeded. {user_role.title()}s are limited to {limit_config['max_requests']} requests per minute.",
                "rate_limit": {
                    "max_requests": limit_config['max_requests'],
                    "window": f"{limit_config['window']} seconds",
                    "retry_after": retry_after
                },
                "status_code": 429
            }), 429
        
        # Add user info to request context
        request.user_id = user_id
        request.user_role = user_role
        request.user_name = user_name
        
        return f(*args, **kwargs)
    
    return decorated_function


# ------------------------------------------------------------
# Product Catalog (ORDS REST API)
# ------------------------------------------------------------
class ProductCatalog:
    def __init__(self, api_url=None):
        self.api_url = api_url or (
            "https://vsnf5ulr.adb.us-ashburn-1.oraclecloudapps.com/"
            "ords/oci_tech_squad_user/api_v1/products/"
        )
        self.products = []
        self.last_updated = None
        self._load_products()

    def _load_products(self):
        try:
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            self.products = []
            for p in data.get("items", []):
                self.products.append({
                    "id": p.get("product_id"),
                    "name": p.get("name"),
                    "category": p.get("category"),
                    "description": p.get("description"),
                    "price": p.get("price"),
                    "stock": p.get("quantity"),
                    "image_url": p.get("image_url"),
                })
            self.last_updated = datetime.now().isoformat()
            return True

        except Exception as e:
            print(f"Product API error: {e}")
            return False

    def refresh(self):
        return self._load_products()

    def get_all_products(self):
        return self.products

    def get_products_summary(self):
        summary = "PRODUCT CATALOG:\n"
        for p in self.products:
            summary += (
                f"- ID: {p['id']}, Name: {p['name']}, "
                f"Category: {p['category']}, "
                f"Price: ${p['price']}, Stock: {p['stock']}, "
                f"Description: {p['description']}\n"
            )
        return summary


# ------------------------------------------------------------
# Shopping Cart (ORDS REST API)
# ------------------------------------------------------------
class ShoppingCart:
    def __init__(self, api_url=None):
        self.api_url = api_url or (
            "https://vsnf5ulr.adb.us-ashburn-1.oraclecloudapps.com/"
            "ords/oci_tech_squad_user/api_v1/cart/"
        )
        self.cart_items = {}
        self.last_updated = None
        self._load_cart()

    def _load_cart(self):
        try:
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Group cart items by user_id
            self.cart_items = {}
            for item in data.get("items", []):
                user_id = str(item.get("user_id", "0"))
                if user_id not in self.cart_items:
                    self.cart_items[user_id] = []
                self.cart_items[user_id].append({
                    "cart_item_id": item.get("cart_item_id"),
                    "product_id": item.get("product_id"),
                    "name": item.get("name"),
                    "price": item.get("price"),
                    "quantity": item.get("quantity"),
                    "image_url": item.get("image_url")
                })
            
            self.last_updated = datetime.now().isoformat()
            return True
        except Exception as e:
            print(f"Cart API error: {e}")
            return False

    def refresh(self):
        return self._load_cart()

    def get_user_cart(self, user_id):
        """Get cart items for specific user"""
        return self.cart_items.get(str(user_id), [])

    def get_cart_summary(self, user_id):
        """Get cart summary for specific user"""
        items = self.get_user_cart(user_id)
        
        if not items:
            return "CART: Empty"
        
        summary = "CURRENT CART:\n"
        total = 0
        for item in items:
            item_total = item['price'] * item['quantity']
            total += item_total
            summary += (
                f"- {item['name']}: "
                f"${item['price']} x {item['quantity']} = ${item_total:.2f}\n"
            )
        summary += f"\nTotal: ${total:.2f}"
        return summary

    def get_cart_count(self, user_id):
        return len(self.get_user_cart(user_id))

    def get_cart_total(self, user_id):
        items = self.get_user_cart(user_id)
        return sum(item['price'] * item['quantity'] for item in items)


# ------------------------------------------------------------
# Shopping Assistant (OCI GenAI)
# ------------------------------------------------------------
class ShoppingAssistant:
    def __init__(self, config_path="config.json"):
        self.cfg = ConfigLoader(config_path)
        self.catalog = ProductCatalog()
        self.cart = ShoppingCart()

        oci_config = oci.config.from_file(
            self.cfg.get("oci", "config_file_path"),
            self.cfg.get("oci", "config_profile"),
        )

        self.client = oci.generative_ai_inference.GenerativeAiInferenceClient(
            config=oci_config,
            service_endpoint=self.cfg.get("service", "endpoint"),
            retry_strategy=oci.retry.NoneRetryStrategy(),
            timeout=(
                self.cfg.get("timeout", "connect_timeout"),
                self.cfg.get("timeout", "read_timeout"),
            ),
        )

    def _build_system_prompt(self, user_id):
        return f"""You are a helpful shopping assistant that can:
1. Recommend products from the catalog
2. Answer questions about products (price, description, stock)
3. Provide information about the user's shopping cart
4. Help with general shopping queries

{self.catalog.get_products_summary()}

{self.cart.get_cart_summary(user_id)}

RESPONSE RULES:
- For product recommendations: List product names clearly
- For cart queries: Provide clear, conversational answers with specific details
- For product info queries: Answer naturally with relevant details
- Always be helpful and concise
- Use the exact product names from the catalog
- When discussing cart items, include quantity and price when relevant
"""

    def _build_chat_request(self, user_message, history, user_id):
        messages = []
        
        # Build system context as SYSTEM role
        messages.append(
            oci.generative_ai_inference.models.Message(
                role=oci.generative_ai_inference.models.Message.ROLE_SYSTEM,
                content=[
                    oci.generative_ai_inference.models.TextContent(
                        text=self._build_system_prompt(user_id)
                    )
                ],
            )
        )

        # Add history messages directly
        for msg in history:
            role_str = msg["role"].upper()
            
            # Map to OCI enum
            if role_str == "USER":
                oci_role = oci.generative_ai_inference.models.Message.ROLE_USER
            elif role_str in ["MODEL", "ASSISTANT"]:
                oci_role = oci.generative_ai_inference.models.Message.ROLE_ASSISTANT
            else:
                continue
            
            messages.append(
                oci.generative_ai_inference.models.Message(
                    role=oci_role,
                    content=[
                        oci.generative_ai_inference.models.TextContent(
                            text=msg["content"]
                        )
                    ],
                )
            )

        # Add current user message
        messages.append(
            oci.generative_ai_inference.models.Message(
                role=oci.generative_ai_inference.models.Message.ROLE_USER,
                content=[
                    oci.generative_ai_inference.models.TextContent(
                        text=user_message
                    )
                ],
            )
        )

        params = self.cfg.get("chat_parameters")
        return oci.generative_ai_inference.models.GenericChatRequest(
            api_format=oci.generative_ai_inference.models.BaseChatRequest.API_FORMAT_GENERIC,
            messages=messages,
            max_tokens=params["max_tokens"],
            temperature=params["temperature"],
            frequency_penalty=params["frequency_penalty"],
            presence_penalty=params["presence_penalty"],
            top_p=params["top_p"],
            top_k=params["top_k"],
        )

    def _build_chat_detail(self, chat_request):
        return oci.generative_ai_inference.models.ChatDetails(
            serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
                model_id=self.cfg.get("service", "model_ocid")
            ),
            chat_request=chat_request,
            compartment_id=self.cfg.get("oci", "compartment_id"),
        )

    def _extract_response_text(self, chat_response):
        data = chat_response.data

        if hasattr(data, "chat_response"):
            return (
                data.chat_response
                .choices[0]
                .message
                .content[0]
                .text
                .strip()
            )

        if hasattr(data, "choices"):
            return (
                data.choices[0]
                .message
                .content[0]
                .text
                .strip()
            )

        try:
            payload = json.loads(str(data))
            return (
                payload["chat_response"]["choices"][0]
                ["message"]["content"][0]["text"]
                .strip()
            )
        except Exception:
            return str(data)

    def refresh_data(self):
        """Refresh cart and catalog data"""
        cart_success = self.cart.refresh()
        catalog_success = self.catalog.refresh()
        return cart_success and catalog_success

    def get_response(self, user_message, history, user_id):
        # Refresh data before each query
        self.refresh_data()
        
        # Debug: Print history to see what roles we're receiving
        print(f"DEBUG - History received: {history}")
        
        start = time.time()
        chat_request = self._build_chat_request(user_message, history, user_id)
        
        # Debug: Print the messages being sent
        print(f"DEBUG - Messages being sent to OCI:")
        for i, msg in enumerate(chat_request.messages):
            print(f"  Message {i}: role={msg.role}")
        
        chat_detail = self._build_chat_detail(chat_request)
        response = self.client.chat(chat_detail)
        elapsed = time.time() - start
        return self._extract_response_text(response), elapsed


# ------------------------------------------------------------
# Flask REST API
# ------------------------------------------------------------
app = Flask(__name__)
CORS(app)

# Global assistant instance
assistant = None

def init_assistant():
    global assistant
    try:
        assistant = ShoppingAssistant()
        return True
    except Exception as e:
        print(f"Failed to initialize assistant: {e}")
        return False


# ------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint (no auth required)"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "assistant_initialized": assistant is not None
    })


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login endpoint - authenticates user against ORDS API"""
    try:
        data = request.get_json()
        
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'username' or 'password' in request body"
            }), 400

        # Call ORDS login API
        login_url = (
            "https://vsnf5ulr.adb.us-ashburn-1.oraclecloudapps.com/"
            "ords/oci_tech_squad_user/api_v1/login"
        )
        
        login_payload = {
            "username": data['username'],
            "password": data['password']
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = requests.post(login_url, json=login_payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            login_data = response.json()
            
            return jsonify({
                "success": True,
                "userId": login_data.get("userId"),
                "userName": login_data.get("userName"),
                "role": login_data.get("role"),
                "message": "Login successful",
                "timestamp": datetime.now().isoformat()
            })
        else:
            return jsonify({
                "success": False,
                "error": "Invalid username or password",
                "status_code": response.status_code
            }), 401

    except requests.exceptions.Timeout:
        return jsonify({
            "success": False,
            "error": "Login API timeout"
        }), 504
    except requests.exceptions.RequestException as e:
        return jsonify({
            "success": False,
            "error": f"Login API error: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/products', methods=['GET'])
@require_auth
def get_products():
    """Get all products (requires auth)"""
    try:
        if not assistant:
            return jsonify({
                "success": False,
                "error": "Assistant not initialized"
            }), 500

        should_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        if should_refresh:
            assistant.catalog.refresh()

        return jsonify({
            "success": True,
            "products": assistant.catalog.get_all_products(),
            "count": len(assistant.catalog.get_all_products()),
            "last_updated": assistant.catalog.last_updated
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/cart', methods=['GET'])
@require_auth
def get_cart():
    """Get user's cart (requires auth)"""
    try:
        if not assistant:
            return jsonify({
                "success": False,
                "error": "Assistant not initialized"
            }), 500

        should_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        if should_refresh:
            assistant.cart.refresh()

        return jsonify({
            "success": True,
            "cart_items": assistant.cart.get_user_cart(request.user_id),
            "item_count": assistant.cart.get_cart_count(request.user_id),
            "total": round(assistant.cart.get_cart_total(request.user_id), 2),
            "last_updated": assistant.cart.last_updated,
            "user_id": request.user_id
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/chat', methods=['POST'])
@require_auth
def chat():
    """Chat endpoint - AI shopping assistant (requires auth)"""
    try:
        if not assistant:
            return jsonify({
                "success": False,
                "error": "Assistant not initialized"
            }), 500

        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'message' in request body"
            }), 400

        user_message = data['message']
        history = data.get('history', [])

        response_text, elapsed = assistant.get_response(
            user_message, 
            history, 
            request.user_id
        )

        return jsonify({
            "success": True,
            "response": response_text,
            "response_time": round(elapsed, 2),
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ------------------------------------------------------------
# Error Handlers
# ------------------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500


# ------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------

if __name__ == '__main__':
    print("=" * 60)
    print("Shopping Assistant REST API")
    print("=" * 60)
    
    if init_assistant():
        print(f"✓ Assistant initialized")
        print(f"✓ Loaded {len(assistant.catalog.get_all_products())} products")
        print()
        print("API Endpoints:")
        print("\nPublic:")
        print("  GET  /api/health")
        print("  POST /api/auth/login")
        print("\nAuthenticated (requires headers):")
        print("  GET  /api/products")
        print("  GET  /api/cart")
        print("  POST /api/chat")
        print("\nRate Limits:")
        print("  User:  10 requests/minute")
        print("  Admin: 50 requests/minute")
        print("=" * 60)
        
        app.run(host='0.0.0.0', port=5000, debug=False)
    else:
        print("✗ Failed to initialize assistant")
        print("Check your config.json and OCI credentials")
