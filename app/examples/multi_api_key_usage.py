"""
Example usage of the Multi-API Key system with rate limiting and automatic rotation.

This example demonstrates how to integrate the multi-API key system with various LLM clients.
"""

import logging
from typing import Any
import openai
from anthropic import Anthropic

from ..config import Config
from ..llm_client_wrapper import create_llm_wrapper

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_openai_client(api_key: str) -> openai.OpenAI:
    """Factory function to create OpenAI client with given API key"""
    return openai.OpenAI(api_key=api_key)


def create_anthropic_client(api_key: str) -> Anthropic:
    """Factory function to create Anthropic client with given API key"""
    return Anthropic(api_key=api_key)


def example_openai_usage():
    """Example of using OpenAI with multi-API key support"""
    config = Config()
    llm_settings = config.llm.get("default")  # or whatever your LLM config key is
    
    if not llm_settings:
        logger.error("No LLM configuration found")
        return
    
    # Create wrapper with OpenAI client factory
    llm_wrapper = create_llm_wrapper(llm_settings, create_openai_client)
    
    def make_chat_request(client, messages, **kwargs):
        """Function to make chat completion request"""
        return client.chat.completions.create(
            model=llm_settings.model,
            messages=messages,
            max_tokens=llm_settings.max_tokens,
            temperature=llm_settings.temperature,
            **kwargs
        )
    
    try:
        # Make a request - the wrapper will handle key rotation automatically
        messages = [
            {"role": "user", "content": "Hello, how are you?"}
        ]
        
        response = llm_wrapper.make_request(make_chat_request, messages)
        
        print("Response:", response.choices[0].message.content)
        
        # Get usage statistics
        stats = llm_wrapper.get_usage_stats()
        print("Usage stats:", stats)
        
        # Get current key info
        current_key = llm_wrapper.get_current_key_info()
        print("Current key:", current_key)
        
    except Exception as e:
        logger.error(f"Request failed: {e}")


def example_anthropic_usage():
    """Example of using Anthropic with multi-API key support"""
    config = Config()
    llm_settings = config.llm.get("default")
    
    if not llm_settings:
        logger.error("No LLM configuration found")
        return
    
    # Create wrapper with Anthropic client factory
    llm_wrapper = create_llm_wrapper(llm_settings, create_anthropic_client)
    
    def make_message_request(client, messages, **kwargs):
        """Function to make message request"""
        return client.messages.create(
            model=llm_settings.model,
            messages=messages,
            max_tokens=llm_settings.max_tokens,
            temperature=llm_settings.temperature,
            **kwargs
        )
    
    try:
        messages = [
            {"role": "user", "content": "Hello, how are you?"}
        ]
        
        response = llm_wrapper.make_request(make_message_request, messages)
        
        print("Response:", response.content[0].text)
        
        # Monitor usage across multiple requests
        for i in range(5):
            response = llm_wrapper.make_request(make_message_request, [
                {"role": "user", "content": f"This is request number {i+1}"}
            ])
            print(f"Request {i+1} completed with key: {llm_wrapper.get_current_key_info()}")
        
        # Final usage stats
        stats = llm_wrapper.get_usage_stats()
        print("Final usage stats:", stats)
        
    except Exception as e:
        logger.error(f"Request failed: {e}")


def example_stress_test():
    """Example stress test to demonstrate key rotation under rate limits"""
    config = Config()
    llm_settings = config.llm.get("default")
    
    if not llm_settings:
        logger.error("No LLM configuration found")
        return
    
    # Use a client factory (OpenAI in this example)
    llm_wrapper = create_llm_wrapper(llm_settings, create_openai_client)
    
    def make_simple_request(client, prompt, **kwargs):
        return client.chat.completions.create(
            model=llm_settings.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,  # Keep responses short for testing
            **kwargs
        )
    
    print("Starting stress test...")
    successful_requests = 0
    failed_requests = 0
    
    # Make many requests to trigger rate limits and key rotation
    for i in range(100):
        try:
            response = llm_wrapper.make_request(
                make_simple_request, 
                f"Count to {i+1}"
            )
            successful_requests += 1
            
            if i % 10 == 0:  # Log every 10th request
                current_key = llm_wrapper.get_current_key_info()
                print(f"Request {i+1}: Success with {current_key}")
                
        except Exception as e:
            failed_requests += 1
            print(f"Request {i+1}: Failed - {e}")
    
    print(f"\nStress test completed:")
    print(f"Successful requests: {successful_requests}")
    print(f"Failed requests: {failed_requests}")
    
    # Final statistics
    stats = llm_wrapper.get_usage_stats()
    print("\nFinal usage statistics:")
    for key_name, key_stats in stats.items():
        print(f"  {key_name}:")
        print(f"    Requests this minute: {key_stats.get('requests_this_minute', 0)}")
        print(f"    Requests this hour: {key_stats.get('requests_this_hour', 0)}")
        print(f"    Consecutive failures: {key_stats.get('consecutive_failures', 0)}")
        print(f"    Is rate limited: {key_stats.get('is_rate_limited', False)}")


if __name__ == "__main__":
    print("Multi-API Key Usage Examples")
    print("=" * 40)
    
    print("\n1. OpenAI Example:")
    example_openai_usage()
    
    print("\n2. Anthropic Example:")
    example_anthropic_usage()
    
    print("\n3. Stress Test Example:")
    example_stress_test()
