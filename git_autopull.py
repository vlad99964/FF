from flask import Flask, request
import subprocess
import hmac
import hashlib

app = Flask(__name__)

# (опционально) секрет для GitHub / GitLab Webhook
SECRET = b'my_webhook_secret'  # тот же, что и в настройке вебхука

@app.route('/git-update', methods=['POST'])
def update():
    # Проверка сигнатуры от GitHub
    signature = request.headers.get('X-Hub-Signature-256')
    if signature:
        sha_name, signature = signature.split('=')
        mac = hmac.new(SECRET, request.data, hashlib.sha256)
        if not hmac.compare_digest(mac.hexdigest(), signature):
            return 'Invalid signature', 403

    # Выполняем git pull
    try:
        subprocess.run(
            ['git', '-C', '/mnt/sdcard/formfactor', 'pull'],
            check=True
        )
        return 'Updated', 200
    except subprocess.CalledProcessError as e:
        return f'Git error: {e}', 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000)
