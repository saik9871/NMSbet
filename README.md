# NMS Betting Site

A betting platform built with Flask and MongoDB.

## Local Development

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the application:
   ```
   python app.py
   ```
4. Visit `http://localhost:5000` in your browser

## Deployment on Railway

### Prerequisites
- A [Railway](https://railway.app/) account
- A [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) account
- A [Twitch Developer](https://dev.twitch.tv/console/apps) account

### Steps

1. Fork or clone this repository
2. Create a new project in Railway
3. Connect your GitHub repository to Railway
4. Set the following environment variables in Railway:
   - `SECRET_KEY`: A random secret key (generate with `openssl rand -hex 24`)
   - `MONGO_URI`: Your MongoDB connection string
   - `TWITCH_CLIENT_ID`: Your Twitch Client ID
   - `TWITCH_CLIENT_SECRET`: Your Twitch Client Secret
   
5. Add the Railway domain to your Twitch Developer Console as an authorized redirect URI:
   ```
   https://your-railway-domain.railway.app/login/authorized
   ```

6. Deploy your application!

## Features

- Twitch OAuth authentication
- Virtual wallet system
- Admin panel for managing users and bets
- Leaderboard to track user performance
- Real-time bet placement 