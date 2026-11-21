import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request
from search import search_results

app = Flask(__name__)


@app.get('/')
def index():
    query = request.args.get('q', '').strip()[:150]
    artist_search = request.args.get('scope') == 'artist'
    category = request.args.get('type', 'all')
    show = request.args.get('show', '20')
    context = search_results(query, artist_search, category, show, app.logger)
    return render_template('index.html', **context)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('FLASK_PORT', '5055')),
            debug=False, use_reloader=False)
