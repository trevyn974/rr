# Pushover Setup Guide for FDD CAD System

## Current Issue
The Pushover credentials in the system are invalid, preventing critical incident notifications from being sent to your phone.

## Step 1: Get Your Pushover User Key

1. **Go to Pushover.net**: https://pushover.net/
2. **Sign in** to your account (or create one if you don't have one)
3. **Copy your User Key** from the main dashboard
   - It should look like: `u1234567890abcdef1234567890abcdef`
   - This is your personal identifier

## Step 2: Create an Application Token

1. **Go to Create Application**: https://pushover.net/apps/build
2. **Fill out the form**:
   - **Name**: `FDD CAD System` (or any name you prefer)
   - **Description**: `Fire Department CAD System Notifications`
   - **Icon**: You can upload a fire department icon or leave blank
3. **Click "Create Application"**
4. **Copy the Application Token** from the results page
   - It should look like: `a1234567890abcdef1234567890abcdef`

## Step 3: Update the Credentials

Once you have both keys, you need to update them in the following files:

### File 1: `cad_system.py` (Lines 159-160)
```python
pushover_user_key: str = "YOUR_USER_KEY_HERE"
pushover_app_token: str = "YOUR_APP_TOKEN_HERE"
```

### File 2: `test_residential_fire_priority.py` (Lines 27-28)
```python
pushover_user_key="YOUR_USER_KEY_HERE",
pushover_app_token="YOUR_APP_TOKEN_HERE",
```

### File 3: `test_pushover_integration.py` (Lines 16-17)
```python
pushover_user_key="YOUR_USER_KEY_HERE",
pushover_app_token="YOUR_APP_TOKEN_HERE",
```

## Step 4: Test the Configuration

After updating the credentials, run:
```bash
python test_pushover_debug.py
```

This will test both credential combinations and tell you which one works.

## Step 5: Test Critical Notifications

Run the full test:
```bash
python test_residential_fire_priority.py
```

This will send a test critical notification for a Residential Fire incident.

## What You'll Receive

Once configured correctly, you'll receive:
- **Critical incidents** (Residential Fire, Structure Fire, etc.): Emergency priority with siren sound
- **High priority incidents** (Vehicle Fire, Wildfire, etc.): High priority with pushover sound  
- **Medium priority incidents** (Medical Emergency, Traffic Collision, etc.): Normal priority with cosmic sound

## Current Invalid Credentials
- User Key: `u91gdp1wbvynt5wmiec45tsf79e6t5` ❌
- App Token: `agunhyfhpg9rik3dr5uedi51vyotaw` ❌

Replace these with your actual credentials from Pushover.net
