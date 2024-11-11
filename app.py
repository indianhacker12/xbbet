from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import razorpay
from datetime import datetime
import random


from razorpay_config import RAZORPAY_API_KEY, RAZORPAY_API_SECRET

# Initialize Razorpay client and Flask app
razorpay_client = razorpay.Client(auth=(RAZORPAY_API_KEY, RAZORPAY_API_SECRET))
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure key
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost/myadmin'  # MySQL database connection
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    pass_hash = db.Column(db.String(200), nullable=False)  # Store hashed password
    wallet_balance = db.Column(db.Float, nullable=False, default=0)

# GameResult model for generic game results
class GameResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    game_name = db.Column(db.String(100), default='Dice Roll')
    result = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    user = db.relationship('User', backref='game_results')

# ColorGameResult model for storing color prediction results
class ColorGameResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    game_name = db.Column(db.String(100), default='Color Prediction')
    prediction = db.Column(db.String(50), nullable=False)
    actual_color = db.Column(db.String(50), nullable=False)
    bet_amount = db.Column(db.Float, nullable=False)
    win = db.Column(db.Boolean, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    user = db.relationship('User', backref='color_game_results')

# OddEvenGameResult model to store bets and results for the Odd/Even game
class OddEvenGameResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    prediction = db.Column(db.String(50), nullable=False)
    result = db.Column(db.String(50), nullable=False)
    bet_amount = db.Column(db.Float, nullable=False)
    win = db.Column(db.Boolean, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    user = db.relationship('User', backref='odd_even_game_results')

# Home route
@app.route('/')
def main():
    return redirect(url_for('login'))

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']
        user = User.query.filter_by(phone=phone).first()
        if user and check_password_hash(user.pass_hash, password):
            session['user_id'] = user.id
            session['name'] = user.name
            return redirect(url_for('account'))
        flash('Invalid login credentials. Please try again.', 'danger')
    return render_template('login.html')

# Signup route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        password = request.form['password']
        existing_user = User.query.filter_by(phone=phone).first()
        if existing_user:
            flash('Phone number already registered. Please login.', 'warning')
            return redirect(url_for('login'))
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(name=name, phone=phone, pass_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully. Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')


# Wallet route
@app.route('/wallet', methods=['GET', 'POST'])
def wallet():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if request.method == 'POST':
        action = request.form.get('action')
        amount = float(request.form.get('amount', 0))
        if action == 'deposit':
            return redirect(url_for('create_order', amount=amount))
        elif action == 'withdraw' and amount <= user.wallet_balance:
            user.wallet_balance -= amount
            db.session.commit()
            flash('Withdrawal successful!', 'success')
        else:
            flash('Insufficient balance or invalid action!', 'danger')
    return render_template('wallet.html', user=user)

# Create order for Razorpay payment
@app.route('/create_order/<float:amount>', methods=['GET'])
def create_order(amount):
    amount_in_paise = int(amount * 100)  # Convert amount to paise
    order_data = {
        'amount': amount_in_paise,
        'currency': 'INR',
        'payment_capture': '1'
    }
    order = razorpay_client.order.create(data=order_data)
    return render_template('pay.html', order_id=order['id'], amount=amount)

# Payment success route
@app.route('/payment_success', methods=['POST'])
def payment_success():
    payment_id = request.form.get('razorpay_payment_id')
    if not payment_id:
        flash("Payment ID not found!", 'danger')
        return redirect(url_for('wallet'))
    
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    
    user = User.query.get(user_id)
    amount = float(request.form.get('amount', 0))
    user.wallet_balance += amount
    db.session.commit()
    flash("Payment Successful!", 'success')
    return redirect(url_for('wallet'))

# Payment failure route
@app.route('/payment_failed', methods=['POST'])
def payment_failed():
    flash("Payment Failed! Please try again.", 'danger')
    return redirect(url_for('wallet'))

# Account route
@app.route('/account', methods=['GET', 'POST'])
def account():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        user.name = request.form['name']
        db.session.commit()
        flash('Profile updated successfully.', 'success')
    return render_template('account.html', user=user)

# Promotion route
@app.route('/promo', methods=['GET', 'POST'])
def promotions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        promo_code = request.form['promo_code']
        valid_codes = ["WELCOME100", "WEEKLYCASHBACK", "REFER100"]
        if promo_code in valid_codes:
            flash(f'Promo code "{promo_code}" redeemed successfully!', 'success')
        else:
            flash('Invalid promo code. Please try again.', 'danger')
    return render_template('promo.html')

# Route for displaying game history
@app.route('/game-history')
def game_history():
    # Check if the user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Fetch each game type's history from the database
    color_game_history = ColorGameResult.query.filter_by(user_id=user_id).order_by(ColorGameResult.timestamp.desc()).all()
    odd_even_game_history = OddEvenGameResult.query.filter_by(user_id=user_id).order_by(OddEvenGameResult.timestamp.desc()).all()
    generic_game_history = GameResult.query.filter_by(user_id=user_id).order_by(GameResult.timestamp.desc()).all()

    # Structure data to pass to the template
    all_games_history = {
        'color_game': color_game_history,
        'odd_even_game': odd_even_game_history,
        'generic_game': generic_game_history
    }

    # Render the game history template
    return render_template('game_history.html', all_games_history=all_games_history)


# Privacy, Terms, and About routes
@app.route('/home')
def home():
    return render_template('home.html')
@app.route('/privacy')
def privacy_policy():
    return render_template('privacy.html')

@app.route('/security')
def security():
    return render_template('security.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/about')
def about():
    return render_template('about.html')

# Contact route
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        flash('Your message has been sent!', 'success')
    return render_template('contact.html')

# @app.route('/color-prediction', methods=['GET', 'POST'])
# def color_prediction():
#     if 'user_id' not in session:
#         return redirect(url_for('login'))
#     user = User.query.get(session['user_id'])

#     if request.method == 'POST':
#         # Get bet amount and selected color from the request
#         bet_amount = float(request.json['bet_amount'])
#         selected_color = request.json['selected_color']

#         # Check if user has enough balance
#         if user.wallet_balance < bet_amount:
#             return jsonify({'status': 'error', 'message': 'Insufficient balance.'}), 400

#         # Deduct bet amount from wallet
#         user.wallet_balance -= bet_amount
#         db.session.commit()

#         # Generate random result for the game
#         winning_color = random.choice(['green', 'red', 'violet'])
#         win = (selected_color == winning_color)

#         # Update wallet balance if the user wins
#         winnings = bet_amount * 1.93 if win else 0
#         user.wallet_balance += winnings
#         db.session.commit()

#         # Store the game result in the database
#         game_result = ColorGameResult(
#             user_id=user.id,
#             prediction=selected_color,
#             actual_color=winning_color,
#             bet_amount=bet_amount,
#             win=win,
#             timestamp=datetime.now()
#         )
#         db.session.add(game_result)
#         db.session.commit()

#         return jsonify({
#             'status': 'success',
#             'result': winning_color,
#             'win': win,
#             'new_balance': user.wallet_balance,
#             'winnings': winnings,
#             'message': 'Congratulations, you won!' if win else 'Sorry, you lost.'
#         })

#     return render_template('color_prediction.html', user=user)


# @app.route('/color-prediction/history', methods=['GET'])
# def color_prediction_history():
#     if 'user_id' not in session:
#         return redirect(url_for('login'))
#     user_id = session['user_id']
#     history = ColorGameResult.query.filter_by(user_id=user_id).order_by(ColorGameResult.timestamp.desc()).all()

#     # Prepare data for JSON response
#     result_history = [
#         {
#             'prediction': result.prediction,
#             'actual_color': result.actual_color,
#             'bet_amount': result.bet_amount,
#             'win': result.win,
#             'timestamp': result.timestamp.strftime('%Y-%m-%d %H:%M:%S')
#         }
#         for result in history
#     ]
#     return jsonify(result_history)


@app.route('/color-prediction', methods=['GET', 'POST'])
def color_prediction():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        data = request.get_json()
        bet_amount = data.get('bet_amount')
        selected_color = data.get('selected_color')

        if user.wallet_balance < bet_amount:
            return jsonify({'status': 'error', 'message': 'Insufficient balance.'}), 400

        user.wallet_balance -= bet_amount
        db.session.commit()

        winning_color = random.choice(['green', 'red', 'violet'])
        win = (selected_color == winning_color)
        winnings = bet_amount * 1.93 if win else 0
        user.wallet_balance += winnings
        db.session.commit()

        game_result = ColorGameResult(
            user_id=user.id,
            prediction=selected_color,
            actual_color=winning_color,
            bet_amount=bet_amount,
            win=win,
            timestamp=datetime.now()
        )
        db.session.add(game_result)
        db.session.commit()

        return jsonify({
            'status': 'success',
            'result': winning_color,
            'win': win,
            'new_balance': user.wallet_balance,
            'winnings': winnings,
            'message': 'Congratulations, you won!' if win else 'Sorry, you lost.'
        })

    return render_template('color_prediction.html', user=user)


@app.route('/color-prediction/history', methods=['GET'])
def color_prediction_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    history = ColorGameResult.query.filter_by(user_id=user_id).order_by(ColorGameResult.timestamp.desc()).all()

    result_history = [
        {
            'prediction': result.prediction,
            'actual_color': result.actual_color,
            'bet_amount': result.bet_amount,
            'win': result.win,
            'timestamp': result.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
        for result in history
    ]
    return jsonify(result_history)

# Odd/Even Game route
@app.route('/odd-even', methods=['GET', 'POST'])
def odd_even_game():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        bet_amount = float(request.form['amount'])
        prediction = request.form['prediction']
        if user.wallet_balance < bet_amount:
            flash('Insufficient balance. Please add more funds to your wallet.', 'danger')
            return redirect(url_for('wallet'))
        user.wallet_balance -= bet_amount
        result = random.choice(['odd', 'even'])
        win = prediction == result
        if win:
            winnings = bet_amount * 1.93
            user.wallet_balance += winnings
            flash(f'Congratulations! You won {winnings:.2f}. The result was {result}.', 'success')
        else:
            flash(f'Sorry, you lost {bet_amount:.2f}. The result was {result}.', 'danger')
        game_result = OddEvenGameResult(user_id=user.id, prediction=prediction, result=result, bet_amount=bet_amount, win=win)
        db.session.add(game_result)
        db.session.commit()
    return render_template('odd_even.html', user=user)


@app.route('/get_balance', methods=['GET'])
def get_balance():
    user_id = request.args.get('user_id')
    user = User.query.get(user_id)
    if user:
        return jsonify({"balance": user.wallet_balance})
    return jsonify({"error": "User not found"}), 404

@app.route('/update_balance', methods=['POST'])
def update_balance():
    data = request.json
    user_id = data.get("user_id")
    new_balance = data.get("new_balance")

    user = User.query.get(user_id)
    if user:
        user.wallet_balance = new_balance
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"error": "User not found"}), 404

# Route for mines game

@app.route('/mines_game', methods=['POST'])
def mines_game():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 403

    user = User.query.get(user_id)
    data = request.json
    bet_amount = data.get("bet_amount")
    game_outcome = data.get("outcome")  # Outcome from Mines game logic

    if user.wallet_balance < bet_amount:
        return jsonify({"status": "error", "message": "Insufficient balance."}), 400

    # Deduct the bet amount
    user.wallet_balance -= bet_amount

    # Apply winnings or losses based on game outcome
    if game_outcome == "win":
        winnings = bet_amount * 2  # Example payout rate for a win
        user.wallet_balance += winnings

    # Store game result in GameResult or specific model for Mines game if created
    db.session.commit()
    return jsonify({
        "status": "success",
        "new_balance": user.wallet_balance,
        "message": "Congratulations, you won!" if game_outcome == "win" else "Sorry, you lost."
    })


if __name__ == '__main__':
    app.run(debug=True)
