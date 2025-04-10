from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
import requests
import secrets
import urllib.parse
import datetime
import functools
from pymongo import MongoClient
from bson.objectid import ObjectId

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SESSION_TYPE'] = 'filesystem'

# Twitch OAuth configuration
TWITCH_CLIENT_ID = '72pwbvq1rhza8ksgdjxm02vf5bhyok'
TWITCH_CLIENT_SECRET = '4302afbtdj2ztuoxlbz2j8p4vz2alx'
TWITCH_REDIRECT_URI = 'http://localhost:5000/login/authorized'
TWITCH_SCOPE = 'user:read:email'

# MongoDB Atlas configuration
MONGO_URI = "mongodb+srv://narayanarawlo56:admin123@nmsbet.mvvie9p.mongodb.net/?retryWrites=true&w=majority&appName=NMSbet"

# Initialize MongoDB client
client = MongoClient(MONGO_URI)
db = client.betting_site  # Database name

# Define collections
users_collection = db.users
bets_collection = db.bets
bet_options_collection = db.bet_options
user_bets_collection = db.user_bets

# Initialize database (create indexes)
def init_db():
    try:
        # Create unique index on twitch_id for users
        users_collection.create_index([("twitch_id", 1)], unique=True)
        
        # Create index for bet options
        bet_options_collection.create_index([("bet_id", 1)])
        
        # Create index for user bets
        user_bets_collection.create_index([("user_id", 1)])
        user_bets_collection.create_index([("bet_id", 1)])
        
        print("✅ MongoDB indexes created successfully!")
        return True
    except Exception as e:
        import traceback
        print(f"Error initializing database: {str(e)}")
        print(traceback.format_exc())
        return False

# Initialize database
init_db()

# Admin middleware
def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page')
            return redirect(url_for('landing'))
        
        user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
        
        if not user or user.get('is_admin') != 1:
            flash('You do not have permission to access this page')
            return redirect(url_for('dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

# Helper function to convert MongoDB _id to string
def format_document(doc):
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

# Routes
@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/login')
def login():
    # Generate a random state to prevent CSRF
    state = secrets.token_hex(16)
    session['oauth_state'] = state
    
    # Build the authorization URL
    params = {
        'client_id': TWITCH_CLIENT_ID,
        'redirect_uri': TWITCH_REDIRECT_URI,
        'response_type': 'code',
        'scope': TWITCH_SCOPE,
        'state': state
    }
    
    auth_url = f"https://id.twitch.tv/oauth2/authorize?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)

@app.route('/logout')
def logout():
    session.pop('access_token', None)
    session.pop('user_id', None)
    session.pop('oauth_state', None)
    flash('You have been logged out')
    return redirect(url_for('landing'))

@app.route('/login/authorized')
def authorized():
    try:
        # Check for error response
        if 'error' in request.args:
            flash(f"Authentication error: {request.args.get('error')}")
            return redirect(url_for('landing'))
        
        # Get authorization code
        code = request.args.get('code')
        if not code:
            flash('No authorization code received')
            return redirect(url_for('landing'))
        
        # Exchange code for token
        token_params = {
            'client_id': TWITCH_CLIENT_ID,
            'client_secret': TWITCH_CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': TWITCH_REDIRECT_URI
        }
        
        token_response = requests.post('https://id.twitch.tv/oauth2/token', data=token_params)
        
        if token_response.status_code != 200:
            flash(f'Failed to obtain access token: {token_response.text}')
            return redirect(url_for('landing'))
        
        token_data = token_response.json()
        access_token = token_data['access_token']
        
        # Get user info from Twitch
        headers = {
            'Client-ID': TWITCH_CLIENT_ID,
            'Authorization': f'Bearer {access_token}'
        }
        
        user_response = requests.get('https://api.twitch.tv/helix/users', headers=headers)
        
        if user_response.status_code != 200:
            flash(f'Failed to fetch user info: {user_response.text}')
            return redirect(url_for('landing'))
        
        user_data = user_response.json()['data'][0]
        twitch_id = user_data['id']
        username = user_data['login']
        email = user_data.get('email', '')
        profile_image_url = user_data.get('profile_image_url', '')
        
        print(f"✅ Got Twitch user data: {username} (ID: {twitch_id})")
        
        # Check if this is the first user (make them admin)
        is_first_user = users_collection.count_documents({}) == 0
        
        # Check if user exists in our database
        existing_user = users_collection.find_one({"twitch_id": twitch_id})
        
        if existing_user:
            # Update user info
            users_collection.update_one(
                {"_id": existing_user["_id"]},
                {"$set": {
                    "username": username,
                    "email": email,
                    "profile_image_url": profile_image_url
                }}
            )
            user_id = str(existing_user["_id"])
            print(f"✅ Updated existing user: {username}")
        else:
            # Create new user
            new_user = {
                "twitch_id": twitch_id,
                "username": username,
                "email": email,
                "profile_image_url": profile_image_url,
                "wallet_balance": 100.0,
                "is_admin": 1 if is_first_user else 0,
                "created_at": datetime.datetime.now()
            }
            
            result = users_collection.insert_one(new_user)
            user_id = str(result.inserted_id)
            
            print(f"✅ Created new user: {username} with $100 wallet balance" + 
                  (" (ADMIN)" if is_first_user else ""))
            
            # If this is the first user, notify them they're an admin
            if is_first_user:
                flash(f'Welcome {username}! As the first user, you have been made an admin.')
        
        session['user_id'] = user_id
        session['access_token'] = access_token
        
        if not is_first_user:
            flash(f'Welcome, {username}!')
            
        return redirect(url_for('dashboard'))
    except Exception as e:
        import traceback
        print(f"❌ Error in authorized route: {str(e)}")
        print(traceback.format_exc())
        flash(f'Error during authentication: {str(e)}')
        return redirect(url_for('landing'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard')
        return redirect(url_for('landing'))
    
    try:
        # Get user info
        user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
        
        if not user:
            session.pop('user_id', None)
            flash('User not found, please log in again')
            return redirect(url_for('landing'))
        
        # Get open bets
        bets_cursor = bets_collection.find({"status": "open"}).sort("created_at", -1)
        
        # Get bet options for each bet and creator info
        bets_list = []
        for bet in bets_cursor:
            bet_id = bet["_id"]
            
            # Get creator info
            creator = users_collection.find_one({"_id": ObjectId(bet["created_by"])})
            bet["creator_username"] = creator["username"] if creator else "Unknown"
            
            # Get options
            options_cursor = bet_options_collection.find({"bet_id": str(bet_id)})
            bet["options"] = list(options_cursor)
            
            # Format document IDs to strings
            bet = format_document(bet)
            bet["options"] = [format_document(opt) for opt in bet["options"]]
            
            bets_list.append(bet)
        
        # Format user document
        user = format_document(user)
        
        return render_template('dashboard.html', user=user, bets=bets_list)
    except Exception as e:
        import traceback
        print(f"❌ Error in dashboard route: {str(e)}")
        print(traceback.format_exc())
        flash(f'Error loading dashboard: {str(e)}')
        return redirect(url_for('landing'))

@app.route('/place_bet', methods=['POST'])
def place_bet():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please log in to place bets'})
    
    bet_id = request.form.get('bet_id')
    option_id = request.form.get('option_id')
    amount = request.form.get('amount')
    
    # Validate inputs
    if not bet_id or not option_id or not amount:
        return jsonify({'success': False, 'message': 'Missing required fields'})
    
    try:
        amount = float(amount)
        if amount <= 0:
            return jsonify({'success': False, 'message': 'Bet amount must be positive'})
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid bet amount'})
    
    try:
        # Get user's current balance
        user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        current_balance = user.get('wallet_balance', 0)
        
        # Check if user has enough funds
        if amount > current_balance:
            return jsonify({'success': False, 'message': 'Insufficient funds'})
        
        # Verify bet is open
        bet = bets_collection.find_one({"_id": ObjectId(bet_id), "status": "open"})
        
        if not bet:
            return jsonify({'success': False, 'message': 'This bet is not open'})
        
        # Verify option belongs to this bet
        option = bet_options_collection.find_one({"_id": ObjectId(option_id), "bet_id": bet_id})
        
        if not option:
            return jsonify({'success': False, 'message': 'Invalid betting option'})
        
        # Check if user already placed a bet on this bet
        existing_bet = user_bets_collection.find_one({
            "user_id": session['user_id'],
            "bet_id": bet_id,
            "status": "active"
        })
        
        if existing_bet:
            return jsonify({'success': False, 'message': 'You already placed a bet on this event'})
        
        # Deduct amount from user's wallet
        new_balance = current_balance - amount
        users_collection.update_one(
            {"_id": ObjectId(session['user_id'])},
            {"$set": {"wallet_balance": new_balance}}
        )
        
        # Record the bet
        user_bet = {
            "user_id": session['user_id'],
            "bet_id": bet_id,
            "option_id": option_id,
            "amount": amount,
            "status": "active",
            "placed_at": datetime.datetime.now()
        }
        
        user_bets_collection.insert_one(user_bet)
        
        return jsonify({
            'success': True, 
            'message': 'Bet placed successfully!',
            'new_balance': f"${new_balance:.2f}"
        })
        
    except Exception as e:
        import traceback
        print(f"❌ Error placing bet: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin/dashboard.html')

@app.route('/admin/users')
@admin_required
def admin_users():
    users_cursor = users_collection.find().sort("username", 1)
    users = [format_document(user) for user in users_cursor]
    return render_template('admin/users.html', users=users)

@app.route('/admin/make_admin/<user_id>', methods=['POST'])
@admin_required
def make_admin(user_id):
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"is_admin": 1}}
    )
    flash('User has been made an admin')
    return redirect(url_for('admin_users'))

@app.route('/admin/remove_admin/<user_id>', methods=['POST'])
@admin_required
def remove_admin(user_id):
    # Don't allow removing yourself as admin
    if user_id == session['user_id']:
        flash('You cannot remove yourself as admin')
        return redirect(url_for('admin_users'))
    
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"is_admin": 0}}
    )
    flash('Admin privileges have been removed')
    return redirect(url_for('admin_users'))

@app.route('/admin/bets')
@admin_required
def admin_bets():
    # Get all bets with creator username
    bets_cursor = bets_collection.find().sort("created_at", -1)
    
    # Get options and creator info for each bet
    bets_list = []
    for bet in bets_cursor:
        bet_id = bet["_id"]
        
        # Get creator info
        creator = None
        if "created_by" in bet:
            creator = users_collection.find_one({"_id": ObjectId(bet["created_by"])})
        
        # Add creator username
        bet["creator_username"] = creator["username"] if creator else "Unknown"
        
        # Get options
        options_cursor = bet_options_collection.find({"bet_id": str(bet_id)})
        bet["options"] = list(options_cursor)
        
        # Format document IDs to strings
        bet = format_document(bet)
        bet["options"] = [format_document(opt) for opt in bet["options"]]
        
        bets_list.append(bet)
    
    return render_template('admin/bets.html', bets=bets_list)

@app.route('/admin/bets/create', methods=['GET', 'POST'])
@admin_required
def create_bet():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        options = request.form.getlist('options[]')
        
        if not title:
            flash('Title is required')
            return redirect(url_for('create_bet'))
        
        if len(options) < 2:
            flash('At least two betting options are required')
            return redirect(url_for('create_bet'))
        
        # Filter out empty options
        options = [opt for opt in options if opt.strip()]
        
        # Create the bet
        bet = {
            "title": title,
            "description": description,
            "created_by": session['user_id'],
            "status": "open",
            "created_at": datetime.datetime.now()
        }
        
        result = bets_collection.insert_one(bet)
        bet_id = str(result.inserted_id)
        
        # Add the options
        for option in options:
            bet_option = {
                "bet_id": bet_id,
                "option_text": option,
                "is_winner": 0
            }
            bet_options_collection.insert_one(bet_option)
        
        flash('Bet created successfully')
        return redirect(url_for('admin_bets'))
    
    return render_template('admin/create_bet.html')

@app.route('/admin/bets/settle/<bet_id>', methods=['GET', 'POST'])
@admin_required
def settle_bet(bet_id):
    # Get the bet
    bet = bets_collection.find_one({"_id": ObjectId(bet_id)})
    
    if not bet:
        flash('Bet not found')
        return redirect(url_for('admin_bets'))
    
    # Get options for this bet
    options_cursor = bet_options_collection.find({"bet_id": str(bet_id)})
    options = list(options_cursor)
    
    if not options:
        flash('No options found for this bet')
        return redirect(url_for('admin_bets'))
    
    if request.method == 'POST':
        winning_option_id = request.form.get('winning_option')
        
        if not winning_option_id:
            flash('You must select a winning option')
            return redirect(url_for('settle_bet', bet_id=bet_id))
        
        try:
            # Update bet status
            bets_collection.update_one(
                {"_id": ObjectId(bet_id)},
                {"$set": {
                    "status": "settled",
                    "settled_by": session['user_id'],
                    "settled_at": datetime.datetime.now()
                }}
            )
            
            # Update winning option
            bet_options_collection.update_one(
                {"_id": ObjectId(winning_option_id)},
                {"$set": {"is_winner": 1}}
            )
            
            # Find all bets on this betting event
            user_bets_cursor = user_bets_collection.find({"bet_id": str(bet_id), "status": "active"})
            user_bets = list(user_bets_cursor)
            
            # Calculate total bet amount and winning bet amount
            total_bet_amount = 0
            winning_bet_amount = 0
            
            for user_bet in user_bets:
                total_bet_amount += user_bet.get('amount', 0)
                if str(user_bet.get('option_id')) == str(winning_option_id):
                    winning_bet_amount += user_bet.get('amount', 0)
            
            # Process each user's bet
            for user_bet in user_bets:
                user_id = user_bet.get('user_id')
                user = users_collection.find_one({"_id": ObjectId(user_id)})
                
                if str(user_bet.get('option_id')) == str(winning_option_id):
                    # This user won!
                    if winning_bet_amount > 0:
                        # Calculate payout using the total pot and their proportion of winning bets
                        user_proportion = user_bet.get('amount', 0) / winning_bet_amount
                        payout = total_bet_amount * user_proportion
                        
                        # Update user's wallet
                        if user:
                            new_balance = user.get('wallet_balance', 0) + payout
                            users_collection.update_one(
                                {"_id": ObjectId(user_id)},
                                {"$set": {"wallet_balance": new_balance}}
                            )
                        
                        # Update bet status and payout
                        user_bets_collection.update_one(
                            {"_id": user_bet.get('_id')},
                            {"$set": {
                                "status": "won",
                                "payout": payout
                            }}
                        )
                    else:
                        # Edge case: no winning bets
                        user_bets_collection.update_one(
                            {"_id": user_bet.get('_id')},
                            {"$set": {"status": "won"}}
                        )
                else:
                    # This user lost
                    user_bets_collection.update_one(
                        {"_id": user_bet.get('_id')},
                        {"$set": {"status": "lost"}}
                    )
            
            flash('Bet settled successfully')
            return redirect(url_for('admin_bets'))
            
        except Exception as e:
            import traceback
            print(f"❌ Error settling bet: {str(e)}")
            print(traceback.format_exc())
            flash(f'Error settling bet: {str(e)}')
            return redirect(url_for('settle_bet', bet_id=bet_id))
    
    # Format documents for the template
    bet = format_document(bet)
    options = [format_document(opt) for opt in options]
    
    return render_template('admin/settle_bet.html', bet=bet, options=options)

@app.route('/leaderboard')
def leaderboard():
    try:
        # Aggregate users with their betting statistics
        pipeline = [
            {
                "$lookup": {
                    "from": "user_bets",
                    "localField": "_id",
                    "foreignField": "user_id",
                    "as": "bets"
                }
            },
            {
                "$addFields": {
                    "wins": {
                        "$size": {
                            "$filter": {
                                "input": "$bets",
                                "as": "bet",
                                "cond": {"$eq": ["$$bet.status", "won"]}
                            }
                        }
                    },
                    "losses": {
                        "$size": {
                            "$filter": {
                                "input": "$bets",
                                "as": "bet",
                                "cond": {"$eq": ["$$bet.status", "lost"]}
                            }
                        }
                    },
                    "profit": {
                        "$reduce": {
                            "input": "$bets",
                            "initialValue": 0,
                            "in": {
                                "$cond": [
                                    {"$eq": ["$$this.status", "won"]},
                                    {"$add": ["$$value", {"$subtract": [{"$ifNull": ["$$this.payout", 0]}, "$$this.amount"]}]},
                                    {"$subtract": ["$$value", "$$this.amount"]}
                                ]
                            }
                        }
                    }
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "username": 1,
                    "profile_image_url": 1,
                    "wallet_balance": 1,
                    "is_admin": 1,
                    "wins": 1,
                    "losses": 1,
                    "profit": 1
                }
            },
            {
                "$sort": {"profit": -1, "wins": -1}
            }
        ]
        
        users_cursor = users_collection.aggregate(pipeline)
        
        # Convert cursor to list and format documents
        leaderboard_data = []
        for idx, user in enumerate(users_cursor):
            user = format_document(user)
            user['rank'] = idx + 1
            
            # Ensure values are not None
            user['wins'] = user.get('wins', 0)
            user['losses'] = user.get('losses', 0)
            user['profit'] = user.get('profit', 0)
            
            # Calculate win rate
            total_bets = user['wins'] + user['losses']
            if total_bets > 0:
                user['win_rate'] = (user['wins'] / total_bets) * 100
            else:
                user['win_rate'] = 0
                
            leaderboard_data.append(user)
        
        # Check if user is logged in
        user_id = session.get('user_id')
        
        # Find current user's rank if logged in
        current_user = None
        if user_id:
            for user in leaderboard_data:
                if user['_id'] == user_id:
                    current_user = user
                    break
        
        return render_template('leaderboard.html', 
                               leaderboard=leaderboard_data, 
                               current_user=current_user)
    
    except Exception as e:
        import traceback
        print(f"❌ Error generating leaderboard: {str(e)}")
        print(traceback.format_exc())
        flash(f'Error loading leaderboard: {str(e)}')
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True) 