import streamlit as st
import openapi_client
from openapi_client.models import ChessCreate, ChessParties, Party, PieceType, PieceColor
import requests
from typing import Dict, List, Callable
from dataclasses import dataclass
import functools

@dataclass
class AuthConfig:
    auth_url: str = "https://keycloak-platformdemo-chess.noumena.cloud/realms/noumena"
    client_id: str = "noumena"
    client_secret: str = "test"

def with_token_refresh(func: Callable):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            if "token" in str(e).lower() or "unauthorized" in str(e).lower():
                try:
                    self.ensure_valid_token()
                    return func(self, *args, **kwargs)
                except ValueError as ve:
                    st.error(str(ve))
                    st.session_state.clear()
                    st.rerun()
            raise e
    return wrapper

class ChessApp:
    def __init__(self):
        self.api_client = None
        self.configuration = openapi_client.Configuration(
            host="https://engine-platformdemo-chess.noumena.cloud"
        )
        self.auth_config = AuthConfig()

    def fetch_access_token(self, username: str, password: str) -> Dict[str, str]:
        url = f"{self.auth_config.auth_url}/protocol/openid-connect/token"

        data = {
            "grant_type": "password",
            "client_id": self.auth_config.client_id,
            "client_secret": self.auth_config.client_secret,
            "username": username,
            "password": password
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            if "access_token" not in token_data or "refresh_token" not in token_data:
                raise ValueError(f"Invalid token response: {token_data}")
                
            return token_data
            
        except Exception as e:
            raise ValueError(f"Failed to fetch access token: {str(e)}")

    def refresh_token(self, refresh_token: str) -> Dict[str, str]:
        url = f"{self.auth_config.auth_url}/protocol/openid-connect/token"

        data = {
            "grant_type": "refresh_token",
            "client_id": self.auth_config.client_id,
            "client_secret": self.auth_config.client_secret,
            "refresh_token": refresh_token
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            if "access_token" not in token_data or "refresh_token" not in token_data:
                raise ValueError(f"Invalid token response: {token_data}")
                
            return token_data
        except Exception as e:
            raise ValueError(f"Failed to refresh token: {str(e)}")

    def ensure_valid_token(self):
        if not st.session_state.get('refresh_token'):
            raise ValueError("No refresh token available. Please login again.")
            
        try:
            token_data = self.refresh_token(st.session_state.refresh_token)
            self.configuration.access_token = token_data["access_token"]
            self.api_client = openapi_client.ApiClient(self.configuration)
            st.session_state.api_client = self.api_client
            st.session_state.auth_token = token_data["access_token"]
            st.session_state.refresh_token = token_data["refresh_token"]
        except Exception as e:
            raise ValueError("Session expired. Please login again.")

    @with_token_refresh
    def create_chess_instance(self, player_username: str, opponent_username: str, player_color: str) -> None:
        if not st.session_state.get('api_client'):
            raise ValueError("Please login first")

        # Use API client from session state
        api_client = st.session_state.api_client
        
        # Debug log the input
        print(f"\nCreating game with: player={player_username}, opponent={opponent_username}, color={player_color}")
        
        # Create parties based on color selection - normalize color to uppercase
        is_white = player_color.upper() == "WHITE"
        white_party = self._username_to_party(player_username if is_white else opponent_username)
        black_party = self._username_to_party(opponent_username if is_white else player_username)
        
        # Debug log the parties
        print(f"White party: {white_party.entity}")
        print(f"Black party: {black_party.entity}")
        
        parties = ChessParties(
            white=white_party,
            black=black_party
        )
        
        chess_create = ChessCreate(parties=parties)
        
        # Create chess instance
        api_instance = openapi_client.DefaultApi(api_client)
        response = api_instance.create_chess(chess_create)
        
        # Debug log the created game
        print(f"Created game: {response.id}")
        print(f"Game state: {response.state}")
        print(f"Game parties: white={response.parties.white.entity}, black={response.parties.black.entity}\n")
        
        return response

    def login(self, username: str, password: str) -> None:
        try:
            token_data = self.fetch_access_token(username, password)
            self.configuration.access_token = token_data["access_token"]
            self.api_client = openapi_client.ApiClient(self.configuration)
            st.session_state.api_client = self.api_client
            st.session_state.username = username
            st.session_state.stored_username = username  # Store username for session restoration
            st.session_state.auth_token = token_data["access_token"]
            st.session_state.refresh_token = token_data["refresh_token"]
            
            st.success("Successfully logged in!")
            st.rerun()
        except Exception as e:
            st.error(f"Login failed: {str(e)}")

    @with_token_refresh
    def get_chess_games(self) -> List[Dict]:
        if not st.session_state.get('api_client'):
            raise ValueError("Please login first")

        api_instance = openapi_client.DefaultApi(st.session_state.api_client)
        response = api_instance.get_chess_list()
        return response.items

    @with_token_refresh
    def get_board(self, game_id: str) -> List[Dict]:
        if not st.session_state.get('api_client'):
            raise ValueError("Please login first")

        api_instance = openapi_client.DefaultApi(st.session_state.api_client)
        return api_instance.chess_get_board(game_id)

    @with_token_refresh
    def get_current_turn(self, game_id: str) -> str:
        if not st.session_state.get('api_client'):
            raise ValueError("Please login first")

        api_instance = openapi_client.DefaultApi(st.session_state.api_client)
        return api_instance.chess_get_current_turn(game_id)

    @with_token_refresh
    def make_move(self, game_id: str, from_pos: str, to_pos: str, current_turn: str) -> None:
        try:
            if not st.session_state.get('api_client'):
                raise ValueError("Please login first")

            # Convert chess notation to internal coordinates
            from_x = ord(from_pos[0].lower()) - ord('a')
            from_y = int(from_pos[1]) - 1
            to_x = ord(to_pos[0].lower()) - ord('a')
            to_y = int(to_pos[1]) - 1

            print(f"Debug - Move from: {from_pos} ({from_x}, {from_y})")
            print(f"Debug - Move to: {to_pos} ({to_x}, {to_y})")

            # Create proper Position and Move objects
            from_position = openapi_client.models.Position(x=from_x, y=from_y)
            to_position = openapi_client.models.Position(x=to_x, y=to_y)
            move = openapi_client.models.Move(var_from=from_position, to=to_position)

            api_instance = openapi_client.DefaultApi(st.session_state.api_client)
            
            if current_turn == PieceColor.WHITE:
                command = openapi_client.models.ChessMakeWhiteMoveCommand(move=move)
                api_instance.chess_make_white_move(game_id, command)
            else:
                command = openapi_client.models.ChessMakeBlackMoveCommand(move=move)
                api_instance.chess_make_black_move(game_id, command)

        except Exception as e:
            # Extract the meaningful part of the error message
            error_msg = str(e)
            if "Invalid move" in error_msg:
                st.error("Invalid move! Please check the rules of chess.")
            elif "Not your turn" in error_msg:
                st.error("Not your turn!")
            else:
                st.error("Move failed. Please try again.")
            raise ValueError("Move failed")  # Simplified error for the caller

    @with_token_refresh
    def get_game(self, game_id: str):
        if not st.session_state.get('api_client'):
            raise ValueError("Please login first")

        api_instance = openapi_client.DefaultApi(st.session_state.api_client)
        return api_instance.get_chess_by_id(game_id)

    def _create_party(self, claims: Dict[str, List[str]]) -> Party:
        return Party(
            entity=claims,
            access={}  # Access claims can be empty for this use case
        )

    def _username_to_party(self, username: str) -> Party:
        return self._create_party({
            "preferred_username": [username],
            "iss": [self.auth_config.auth_url]
        })

def display_board(pieces, is_white: bool = True):
    """Display the chess board using Unicode chess pieces."""
    # Create empty board
    board = [[None for _ in range(8)] for _ in range(8)]
    
    # Detect theme
    is_dark_mode = st.get_option("theme.base") == "dark"
    
    # CSS for the chessboard
    st.markdown("""
        <style>
        .chess-board {
            font-family: monospace;
            font-size: 24px;
            line-height: 1.2;
            white-space: pre;
            background-color: #2c2c2c;
            display: inline-block;
            padding: 10px;
            border-radius: 5px;
        }
        .square-light {
            background-color: #f0d9b5;
            padding: 5px 10px;
            display: inline-block;
            width: 40px;
            height: 40px;
            text-align: center;
            vertical-align: middle;
        }
        .square-dark {
            background-color: #b58863;
            padding: 5px 10px;
            display: inline-block;
            width: 40px;
            height: 40px;
            text-align: center;
            vertical-align: middle;
        }
        .piece-white {
            color: rgba(255, 255, 255, 0.95);
            text-shadow: 0 0 2px rgba(0, 0, 0, 0.4);
        }
        .piece-black {
            color: rgba(0, 0, 0, 0.95);
            text-shadow: 0 0 2px rgba(255, 255, 255, 0.4);
        }
        .coordinate {
            color: #f0f0f0;
            display: inline-block;
            width: 40px;
            height: 40px;
            text-align: center;
            line-height: 50px;
            vertical-align: middle;
        }
        .coordinate-row {
            color: #f0f0f0;
            width: 20px;
            padding: 0 10px;
        }
        </style>
    """, unsafe_allow_html=True)

    # Define single set of piece symbols
    pieces_unicode = {
        PieceType.PAWN: "♟",
        PieceType.ROOK: "♜",
        PieceType.KNIGHT: "♞",
        PieceType.BISHOP: "♝",
        PieceType.QUEEN: "♛",
        PieceType.KING: "♚"
    }
    
    # Place pieces on board
    for piece in pieces:
        y = 7 - piece.position.y  # Flip y since we display rank 1 at the bottom
        x = piece.position.x      # x is already correct (a=0, h=7)
        board[y][x] = piece
    
    # Generate HTML for the board
    html = ['<div class="chess-board">']
    
    # Add column coordinates at the top
    html.append('<div><span class="coordinate-row"> </span>')
    for col in 'abcdefgh':
        html.append(f'<span class="coordinate">{col}</span>')
    html.append('<span class="coordinate-row"> </span></div>')
    
    # Add rows with row coordinates
    for i, row in enumerate(board):
        html.append(f'<div><span class="coordinate-row">{8-i}</span>')
        for j, piece in enumerate(row):
            is_light = (i + j) % 2 == 1
            square_class = "square-light" if is_light else "square-dark"
            piece_class = ""
            symbol = " "
            if piece is not None:
                piece_class = " piece-white" if piece.color == PieceColor.WHITE else " piece-black"
                symbol = pieces_unicode[piece.type]
            html.append(f'<span class="{square_class}{piece_class}">{symbol}</span>')
        html.append(f'<span class="coordinate-row">{8-i}</span></div>')
    
    # Add column coordinates at the bottom
    html.append('<div><span class="coordinate-row"> </span>')
    for col in 'abcdefgh':
        html.append(f'<span class="coordinate">{col}</span>')
    html.append('<span class="coordinate-row"> </span></div>')
    
    html.append('</div>')
    
    # Display the board
    st.markdown(''.join(html), unsafe_allow_html=True)

def main():
    # Initialize session state
    if 'username' not in st.session_state:
        st.session_state.username = None
    if 'stored_username' not in st.session_state:
        st.session_state.stored_username = None
    if 'api_client' not in st.session_state:
        st.session_state.api_client = None
    if 'auth_token' not in st.session_state:
        st.session_state.auth_token = None
    if 'refresh_token' not in st.session_state:
        st.session_state.refresh_token = None
    if 'show_create_form' not in st.session_state:
        st.session_state.show_create_form = False
    if 'active_game_id' not in st.session_state:
        st.session_state.active_game_id = None

    app = ChessApp()

    # Try to restore session if we have a token
    if not st.session_state.username and st.session_state.auth_token and st.session_state.refresh_token:
        try:
            app.ensure_valid_token()
            # If token refresh successful, set username from stored token
            st.session_state.username = st.session_state.get('stored_username')
        except ValueError:
            st.session_state.clear()
            st.rerun()

    # Login section
    if not st.session_state.username:
        st.header("Login")
        with st.form("login_form"):
            col1, col2 = st.columns(2)
            with col1:
                username = st.text_input("Username")
            with col2:
                password = st.text_input("Password", type="password")
            
            submit = st.form_submit_button("Login")
            if submit:
                if username and password:
                    app.login(username, password)
                else:
                    st.error("Please enter both username and password")
    else:
        # Top bar with user info and logout
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            st.write(f"Logged in as: {st.session_state.username}")
        with col3:
            if st.button("Logout"):
                st.session_state.clear()
                st.rerun()

        # Main content
        if st.session_state.active_game_id:
            st.header(f"Game: {st.session_state.active_game_id}")
            
            # Back button
            if st.button("Back to Games List"):
                st.session_state.active_game_id = None
                st.rerun()

            try:
                # Get game details and current state
                game = app.get_game(st.session_state.active_game_id)
                board = app.get_board(st.session_state.active_game_id)
                current_turn = app.get_current_turn(st.session_state.active_game_id)
                
                # Get player's color in this game
                is_white = st.session_state.username == game.parties.white.entity.get("preferred_username")[0]
                player_color = PieceColor.WHITE if is_white else PieceColor.BLACK
                
                # Display game state
                st.subheader("Game Status")
                if current_turn == player_color:
                    st.success("🎯 Your turn!")
                else:
                    st.info("⏳ Waiting for opponent's move...")
                
                # Show player info
                col1, col2 = st.columns(2)
                with col1:
                    st.write("You: " + ("White ⚪" if is_white else "Black ⚫"))
                with col2:
                    st.write("Opponent: " + ("Black ⚫" if is_white else "White ⚪"))
                
                # Display the board from player's perspective
                display_board(board, is_white=is_white)
                
                # Show move input only if it's the player's turn
                if current_turn == player_color:
                    with st.form("move_form"):
                        st.write("Enter moves in chess notation (e.g., 'e2' for starting position, 'e4' for destination)")
                        col1, col2 = st.columns(2)
                        with col1:
                            from_square = st.text_input("From square", help="e.g., 'e7' for black's pawn")
                        with col2:
                            to_square = st.text_input("To square", help="e.g., 'e6' for black's pawn")
                        
                        # Basic validation
                        valid_input = True
                        if from_square and to_square:
                            if not (len(from_square) == 2 and len(to_square) == 2):
                                st.error("Squares must be in format like 'e2'")
                                valid_input = False
                            if not (from_square[0] in 'abcdefgh' and to_square[0] in 'abcdefgh'):
                                st.error("File must be between 'a' and 'h'")
                                valid_input = False
                            if not (from_square[1] in '12345678' and to_square[1] in '12345678'):
                                st.error("Rank must be between 1 and 8")
                                valid_input = False
                            
                            # Add help text based on player's color
                            if is_white:
                                st.info("White pieces start on ranks 1 and 2")
                            else:
                                st.info("Black pieces start on ranks 7 and 8")
                        
                        submit = st.form_submit_button("Make Move")
                        if submit and valid_input and from_square and to_square:
                            try:
                                app.make_move(
                                    st.session_state.active_game_id,
                                    from_square.lower(),
                                    to_square.lower(),
                                    current_turn
                                )
                                st.rerun()
                            except ValueError as e:
                                # Error already displayed by make_move
                                pass
            except Exception as e:
                st.error(f"Error loading game: {str(e)}")

        elif st.session_state.show_create_form:
            st.header("Create New Game")
            
            # Back button outside the form
            if st.button("Back to Games List"):
                st.session_state.show_create_form = False
                st.rerun()
            
            with st.form("create_game_form"):
                opponent_username = st.text_input("Opponent's username")
                player_color = st.selectbox("Select your color", ["White", "Black"])
                print(f"Debug - Selected color: {player_color}")  # Debug the selected color
                
                submit = st.form_submit_button("Create Game")
                if submit:
                    if not opponent_username:
                        st.error("Please enter opponent's username")
                    else:
                        try:
                            app.create_chess_instance(
                                st.session_state.username,
                                opponent_username,
                                player_color
                            )
                            st.success("Chess game created successfully!")
                            st.session_state.show_create_form = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creating chess instance: {str(e)}")
        else:
            # Games list view
            st.header("Your Chess Games")
            
            col1, col2 = st.columns([4, 1])
            with col2:
                if st.button("Create New Game"):
                    st.session_state.show_create_form = True
                    st.rerun()

            try:
                games = app.get_chess_games()
                if not games:
                    st.info("No games found. Create a new game to get started!")
                else:
                    for game in games:
                        with st.container():
                            col1, col2, col3 = st.columns([2, 2, 1])
                            with col1:
                                st.write(f"Game ID: {game.id}")
                            with col2:
                                st.write(f"State: {game.state}")
                            with col3:
                                if st.button("View Game", key=game.id):
                                    st.session_state.active_game_id = game.id
                                    st.rerun()
                            st.divider()
            except Exception as e:
                st.error(f"Error fetching games: {str(e)}")

if __name__ == "__main__":
    main() 