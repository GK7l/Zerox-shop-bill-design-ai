# Free Hosting on PythonAnywhere

This Flask app can be hosted for free on PythonAnywhere.

Your final website URL will be:

```text
https://YOUR_USERNAME.pythonanywhere.com
```

Replace `YOUR_USERNAME` with your PythonAnywhere username.

## 1. Create Free Account

Go to:

```text
https://www.pythonanywhere.com
```

Create a free beginner account.

## 2. Open Bash Console

In PythonAnywhere:

1. Open **Consoles**
2. Start a **Bash** console
3. Run:

```bash
git clone https://github.com/GK7l/Zerox-shop-bill-design-ai.git
cd Zerox-shop-bill-design-ai
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Create Web App

1. Go to the **Web** tab
2. Click **Add a new web app**
3. Choose **Manual configuration**
4. Choose Python 3.13

## 4. Set Virtualenv

In the **Web** tab, find **Virtualenv** and enter:

```text
/home/YOUR_USERNAME/Zerox-shop-bill-design-ai/venv
```

## 5. Edit WSGI File

In the **Web** tab, click the WSGI configuration file link.

Delete the sample code and paste this:

```python
import sys

path = '/home/YOUR_USERNAME/Zerox-shop-bill-design-ai'
if path not in sys.path:
    sys.path.insert(0, path)

from app import app as application
```

Replace `YOUR_USERNAME` with your PythonAnywhere username.

## 6. Add Static Files

In the **Web** tab, under **Static files**, add:

```text
URL: /static/
Directory: /home/YOUR_USERNAME/Zerox-shop-bill-design-ai/static/
```

## 7. Reload Website

Click **Reload** in the Web tab.

Open:

```text
https://YOUR_USERNAME.pythonanywhere.com
```

## Login

Default login:

```text
Username: admin
Password: admin
```

or

```text
Username: ganesh
Password: IT
```

## Important

PythonAnywhere free accounts are good for testing and small use. Your free URL depends on your PythonAnywhere username.
