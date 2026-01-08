"""
Test script for Shopping Assistant API endpoints
Tests: Health, Login, Products, Cart, Chat
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:5000"
TEST_USER = {
    "username": "john.doe",
    "password": "Welcome@123"
}

# Store auth info
auth_headers = {}


def print_section(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def print_response(response):
    print(f"Status: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response: {response.text}")
    print()


def test_health():
    print_section("1. Testing Health Check")
    response = requests.get(f"{BASE_URL}/api/health")
    print_response(response)
    return response.status_code == 200


def test_login():
    print_section("2. Testing Login")
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=TEST_USER
    )
    print_response(response)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            auth_headers['X-User-ID'] = str(data['userId'])
            auth_headers['X-User-Role'] = data['role']
            auth_headers['X-User-Name'] = data['userName']
            print(f"✓ Logged in as: {data['userName']} (Role: {data['role']}, ID: {data['userId']})")
            return True
    
    print("✗ Login failed")
    return False


def test_products():
    print_section("3. Testing Products Endpoint")
    
    # Test without auth (should fail)
    print("3a. Without authentication:")
    response = requests.get(f"{BASE_URL}/api/products")
    print_response(response)
    
    # Test with auth
    print("3b. With authentication:")
    response = requests.get(
        f"{BASE_URL}/api/products",
        headers=auth_headers
    )
    print_response(response)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Found {data.get('count', 0)} products")
        return True
    
    print("✗ Products fetch failed")
    return False


def test_cart():
    print_section("4. Testing Cart Endpoint")
    
    # Test without auth (should fail)
    print("4a. Without authentication:")
    response = requests.get(f"{BASE_URL}/api/cart")
    print_response(response)
    
    # Test with auth
    print("4b. With authentication:")
    response = requests.get(
        f"{BASE_URL}/api/cart",
        headers=auth_headers
    )
    print_response(response)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Cart has {data.get('item_count', 0)} items, Total: ${data.get('total', 0)}")
        
        # Display cart items
        if data.get('cart_items'):
            print("\nCart Items:")
            for item in data['cart_items']:
                print(f"  - {item['name']}: ${item['price']} x {item['quantity']}")
        
        return True
    
    print("✗ Cart fetch failed")
    return False


def test_chat():
    print_section("5. Testing Chat Endpoint")
    
    # Test without auth (should fail)
    print("5a. Without authentication:")
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={"message": "Hello"}
    )
    print_response(response)
    
    # Test with auth - simple query
    print("5b. Simple chat query (What products do you have?):")
    response = requests.post(
        f"{BASE_URL}/api/chat",
        headers=auth_headers,
        json={
            "message": "What products do you have?",
            "history": []
        }
    )
    print_response(response)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Chat response received in {data.get('response_time', 0)}s")
        
        # Test with history
        print("5c. Chat with history (What's in my cart?):")
        response = requests.post(
            f"{BASE_URL}/api/chat",
            headers=auth_headers,
            json={
                "message": "What's in my cart?",
                "history": [
                    {"role": "user", "content": "What products do you have?"},
                    {"role": "model", "content": data.get('response', '')}
                ]
            }
        )
        print_response(response)
        
        if response.status_code == 200:
            print("✓ Chat with history successful")
            
            # Test product recommendation
            print("5d. Product recommendation:")
            response = requests.post(
                f"{BASE_URL}/api/chat",
                headers=auth_headers,
                json={
                    "message": "Recommend me some electronics under $30",
                    "history": []
                }
            )
            print_response(response)
            
            return response.status_code == 200
        else:
            print("✗ Chat with history failed")
            return False
    
    print("✗ Chat failed")
    return False


def test_invalid_endpoint():
    print_section("6. Testing Invalid Endpoint (404)")
    response = requests.get(f"{BASE_URL}/api/invalid")
    print_response(response)
    return response.status_code == 404


def test_invalid_login():
    print_section("7. Testing Invalid Login")
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "invalid", "password": "wrong"}
    )
    print_response(response)
    return response.status_code == 401


def run_all_tests():
    print("\n" + "█" * 60)
    print(" SHOPPING ASSISTANT API TEST SUITE")
    print("█" * 60)
    print(f"\nTesting API at: {BASE_URL}")
    print(f"Test user: {TEST_USER['username']}")
    
    results = {
        "Health Check": test_health(),
        "Login (Valid)": test_login(),
        "Login (Invalid)": test_invalid_login(),
        "Products": test_products() if auth_headers else False,
        "Cart": test_cart() if auth_headers else False,
        "Chat": test_chat() if auth_headers else False,
        "404 Handling": test_invalid_endpoint()
    }
    
    # Summary
    print_section("TEST SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} | {test}")
    
    print("\n" + "-" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60 + "\n")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Check the output above.")


if __name__ == '__main__':
    try:
        run_all_tests()
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to API")
        print(f"Make sure the server is running at {BASE_URL}")
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")