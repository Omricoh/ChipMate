import { Component, OnInit, OnDestroy, ViewChild, ElementRef, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { interval, Subscription } from 'rxjs';
import { GameService, GameState, Player, Card } from '../../services/game.service';
import { ChatService } from '../../services/chat.service';
import { AuthService } from '../../services/auth.service';

interface ChatMessage {
  username: string;
  message: string;
  timestamp: Date;
  isSystem?: boolean;
}

interface Transaction {
  id: string;
  fromPlayerId: string;
  toPlayerId: string;
  amount: number;
  timestamp: Date;
  fromPlayerName?: string;
  toPlayerName?: string;
}

interface PlayerWithFormattedBalance extends Player {
  formattedBalance?: string;
}

@Component({
  selector: 'app-game',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './game.component.html',
  styleUrls: ['./game.component.css']
})
export class GameComponent implements OnInit, OnDestroy {
  @ViewChild('chatMessages') private chatMessagesContainer!: ElementRef;
  @ViewChild('transactionsList') private transactionsListContainer!: ElementRef;

  gameId: string = '';
  game: GameState | null = null;
  currentPlayer: Player | null = null;
  currentUserId: string | null = null;
  chatMessage: string = '';
  chatMessages: ChatMessage[] = [];
  copySuccess: boolean = false;
  showTransactionModal: boolean = false;
  selectedPlayerId: string = '';
  transactionAmount: number = 0;
  transactionError: string = '';
  showTransactionHistory: boolean = false;
  transactions: Transaction[] = [];
  showPlayerList: boolean = false;
  selectedCard: Card | null = null;
  showCardModal: boolean = false;
  
  // New properties for mobile buy-in
  showMobileBuyIn: boolean = false;
  mobileBuyInAmount: number = 0;
  buyInError: string = '';

  private gameSubscription?: Subscription;
  private chatSubscription?: Subscription;
  private pollSubscription?: Subscription;

  // Auto-scroll flags
  private shouldAutoScrollChat: boolean = true;
  private shouldAutoScrollTransactions: boolean = true;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private gameService: GameService,
    private chatService: ChatService,
    private authService: AuthService
  ) {}

  ngOnInit() {
    this.gameId = this.route.snapshot.paramMap.get('id') || '';
    this.currentUserId = this.authService.getCurrentUserId();
    
    if (!this.gameId) {
      console.error('No game ID provided');
      this.router.navigate(['/lobby']);
      return;
    }

    this.loadGame();
    this.loadTransactions();
    this.setupPolling();
    this.setupSubscriptions();
  }

  ngOnDestroy() {
    this.cleanup();
  }

  private cleanup() {
    if (this.gameSubscription) {
      this.gameSubscription.unsubscribe();
    }
    if (this.chatSubscription) {
      this.chatSubscription.unsubscribe();
    }
    if (this.pollSubscription) {
      this.pollSubscription.unsubscribe();
    }
  }

  private setupPolling() {
    // Poll every 2 seconds
    this.pollSubscription = interval(2000).subscribe(() => {
      this.loadGame();
      this.loadTransactions();
    });
  }

  private setupSubscriptions() {
    // Subscribe to game state changes
    this.gameSubscription = this.gameService.getGameState(this.gameId).subscribe({
      next: (game) => {
        this.game = game;
        this.updateCurrentPlayer();
      },
      error: (error) => {
        console.error('Error loading game:', error);
      }
    });

    // Subscribe to chat messages
    this.chatSubscription = this.chatService.getMessages(this.gameId).subscribe({
      next: (messages) => {
        this.chatMessages = messages.map(msg => ({
          username: msg.username,
          message: msg.message,
          timestamp: new Date(msg.timestamp),
          isSystem: msg.isSystem
        }));
        this.scrollChatToBottom();
      },
      error: (error) => {
        console.error('Error loading chat messages:', error);
      }
    });
  }

  private loadGame() {
    this.gameService.getGameState(this.gameId).subscribe({
      next: (game) => {
        this.game = game;
        this.updateCurrentPlayer();
      },
      error: (error) => {
        console.error('Error loading game:', error);
        if (error.status === 404) {
          this.router.navigate(['/lobby']);
        }
      }
    });
  }

  private updateCurrentPlayer() {
    if (this.game && this.currentUserId) {
      this.currentPlayer = this.game.players.find(p => p.userId === this.currentUserId) || null;
    }
  }

  private loadTransactions() {
    this.gameService.getTransactions(this.gameId).subscribe({
      next: (transactions) => {
        this.transactions = transactions.map(t => ({
          ...t,
          timestamp: new Date(t.timestamp)
        }));
        this.scrollTransactionsToBottom();
      },
      error: (error) => {
        console.error('Error loading transactions:', error);
      }
    });
  }

  sendMessage() {
    if (!this.chatMessage.trim() || !this.currentPlayer) {
      return;
    }

    this.chatService.sendMessage(this.gameId, this.currentPlayer.name, this.chatMessage).subscribe({
      next: () => {
        this.chatMessage = '';
      },
      error: (error) => {
        console.error('Error sending message:', error);
      }
    });
  }

  @HostListener('window:keydown', ['$event'])
  handleKeyboardEvent(event: KeyboardEvent) {
    // Check if Ctrl+Enter (or Cmd+Enter on Mac) is pressed
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      this.sendMessage();
    }
  }

  private scrollChatToBottom() {
    if (this.shouldAutoScrollChat) {
      setTimeout(() => {
        if (this.chatMessagesContainer) {
          const element = this.chatMessagesContainer.nativeElement;
          element.scrollTop = element.scrollHeight;
        }
      }, 100);
    }
  }

  private scrollTransactionsToBottom() {
    if (this.shouldAutoScrollTransactions) {
      setTimeout(() => {
        if (this.transactionsListContainer) {
          const element = this.transactionsListContainer.nativeElement;
          element.scrollTop = element.scrollHeight;
        }
      }, 100);
    }
  }

  onChatScroll() {
    if (this.chatMessagesContainer) {
      const element = this.chatMessagesContainer.nativeElement;
      const isAtBottom = element.scrollHeight - element.scrollTop <= element.clientHeight + 50;
      this.shouldAutoScrollChat = isAtBottom;
    }
  }

  onTransactionsScroll() {
    if (this.transactionsListContainer) {
      const element = this.transactionsListContainer.nativeElement;
      const isAtBottom = element.scrollHeight - element.scrollTop <= element.clientHeight + 50;
      this.shouldAutoScrollTransactions = isAtBottom;
    }
  }

  copyGameLink() {
    const gameLink = `${window.location.origin}/game/${this.gameId}`;
    navigator.clipboard.writeText(gameLink).then(() => {
      this.copySuccess = true;
      setTimeout(() => {
        this.copySuccess = false;
      }, 2000);
    });
  }

  leaveGame() {
    if (!this.currentPlayer) return;

    if (confirm('Are you sure you want to leave this game?')) {
      this.gameService.leaveGame(this.gameId, this.currentPlayer.id).subscribe({
        next: () => {
          this.router.navigate(['/lobby']);
        },
        error: (error) => {
          console.error('Error leaving game:', error);
          alert('Failed to leave game. Please try again.');
        }
      });
    }
  }

  openTransactionModal(playerId: string) {
    this.selectedPlayerId = playerId;
    this.transactionAmount = 0;
    this.transactionError = '';
    this.showTransactionModal = true;
  }

  closeTransactionModal() {
    this.showTransactionModal = false;
    this.selectedPlayerId = '';
    this.transactionAmount = 0;
    this.transactionError = '';
  }

  submitTransaction() {
    if (!this.currentPlayer || !this.selectedPlayerId) return;

    if (this.transactionAmount <= 0) {
      this.transactionError = 'Amount must be greater than 0';
      return;
    }

    if (this.transactionAmount > this.currentPlayer.balance) {
      this.transactionError = 'Insufficient balance';
      return;
    }

    this.gameService.createTransaction(
      this.gameId,
      this.currentPlayer.id,
      this.selectedPlayerId,
      this.transactionAmount
    ).subscribe({
      next: () => {
        this.closeTransactionModal();
        this.loadGame();
        this.loadTransactions();
      },
      error: (error) => {
        console.error('Error creating transaction:', error);
        this.transactionError = error.error?.error || 'Failed to create transaction';
      }
    });
  }

  toggleTransactionHistory() {
    this.showTransactionHistory = !this.showTransactionHistory;
    if (this.showTransactionHistory) {
      this.loadTransactions();
    }
  }

  togglePlayerList() {
    this.showPlayerList = !this.showPlayerList;
  }

  getPlayerName(playerId: string): string {
    if (!this.game) return 'Unknown';
    const player = this.game.players.find(p => p.id === playerId);
    return player ? player.name : 'Unknown';
  }

  getOtherPlayers(): Player[] {
    if (!this.game || !this.currentPlayer) return [];
    return this.game.players.filter(p => p.id !== this.currentPlayer!.id);
  }

  // Add method to get players with formatted balance
  getPlayersWithFormattedBalance(): PlayerWithFormattedBalance[] {
    if (!this.game) return [];
    return this.game.players.map(player => ({
      ...player,
      formattedBalance: this.formatBalance(player.balance)
    }));
  }

  // Add method to format balance
  formatBalance(balance: number): string {
    return balance.toLocaleString('en-US', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2
    });
  }

  drawCard() {
    if (!this.currentPlayer) return;

    this.gameService.drawCard(this.gameId, this.currentPlayer.id).subscribe({
      next: (card) => {
        this.selectedCard = card;
        this.showCardModal = true;
        this.loadGame(); // Reload to update deck count
      },
      error: (error) => {
        console.error('Error drawing card:', error);
        alert(error.error?.error || 'Failed to draw card');
      }
    });
  }

  closeCardModal() {
    this.showCardModal = false;
    this.selectedCard = null;
  }

  canDrawCard(): boolean {
    return this.game?.settings?.enableCardDeck === true && (this.game?.deckCount || 0) > 0;
  }

  // Mobile buy-in methods
  openMobileBuyIn() {
    this.showMobileBuyIn = true;
    this.mobileBuyInAmount = 0;
    this.buyInError = '';
  }

  closeMobileBuyIn() {
    this.showMobileBuyIn = false;
    this.mobileBuyInAmount = 0;
    this.buyInError = '';
  }

  submitMobileBuyIn() {
    if (!this.currentPlayer) return;

    if (this.mobileBuyInAmount <= 0) {
      this.buyInError = 'Amount must be greater than 0';
      return;
    }

    this.gameService.addBuyIn(this.gameId, this.currentPlayer.id, this.mobileBuyInAmount).subscribe({
      next: () => {
        this.closeMobileBuyIn();
        this.loadGame();
      },
      error: (error) => {
        console.error('Error adding buy-in:', error);
        this.buyInError = error.error?.error || 'Failed to add buy-in';
      }
    });
  }

  // Desktop buy-in methods (for the player list)
  buyIn(player: Player, event: Event) {
    event.stopPropagation();
    const amount = prompt('Enter buy-in amount:');
    if (amount) {
      const numAmount = parseFloat(amount);
      if (isNaN(numAmount) || numAmount <= 0) {
        alert('Invalid amount');
        return;
      }

      this.gameService.addBuyIn(this.gameId, player.id, numAmount).subscribe({
        next: () => {
          this.loadGame();
        },
        error: (error) => {
          console.error('Error adding buy-in:', error);
          alert(error.error?.error || 'Failed to add buy-in');
        }
      });
    }
  }

  cashOut(player: Player, event: Event) {
    event.stopPropagation();
    if (confirm(`Cash out ${player.name} for $${this.formatBalance(player.balance)}?`)) {
      this.gameService.cashOut(this.gameId, player.id).subscribe({
        next: () => {
          this.loadGame();
        },
        error: (error) => {
          console.error('Error cashing out:', error);
          alert(error.error?.error || 'Failed to cash out');
        }
      });
    }
  }

  // Method to check if current user is the game creator
  isCreator(): boolean {
    if (!this.game || !this.currentUserId) return false;
    return this.game.createdBy === this.currentUserId;
  }

  // Add method to format transaction dates
  formatTransactionDate(dateString: string | Date): string {
    const date = typeof dateString === 'string' ? new Date(dateString) : dateString;
    const now = new Date();
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffInSeconds < 60) {
      return 'just now';
    } else if (diffInSeconds < 3600) {
      const minutes = Math.floor(diffInSeconds / 60);
      return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    } else if (diffInSeconds < 86400) {
      const hours = Math.floor(diffInSeconds / 3600);
      return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    } else {
      const days = Math.floor(diffInSeconds / 86400);
      if (days === 1) {
        return 'yesterday';
      } else if (days < 7) {
        return `${days} days ago`;
      } else {
        return date.toLocaleDateString('en-US', { 
          month: 'short', 
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });
      }
    }
  }

  updateBigBlind() {
    if (!this.game) return;

    const newBigBlind = prompt('Enter new big blind amount:', this.game.bigBlind.toString());
    if (newBigBlind) {
      const amount = parseFloat(newBigBlind);
      if (isNaN(amount) || amount <= 0) {
        alert('Invalid amount');
        return;
      }

      this.gameService.updateBigBlind(this.gameId, amount).subscribe({
        next: () => {
          this.loadGame();
        },
        error: (error) => {
          console.error('Error updating big blind:', error);
          alert(error.error?.error || 'Failed to update big blind');
        }
      });
    }
  }

  updateSmallBlind() {
    if (!this.game) return;

    const newSmallBlind = prompt('Enter new small blind amount:', this.game.smallBlind.toString());
    if (newSmallBlind) {
      const amount = parseFloat(newSmallBlind);
      if (isNaN(amount) || amount <= 0) {
        alert('Invalid amount');
        return;
      }

      this.gameService.updateSmallBlind(this.gameId, amount).subscribe({
        next: () => {
          this.loadGame();
        },
        error: (error) => {
          console.error('Error updating small blind:', error);
          alert(error.error?.error || 'Failed to update small blind');
        }
      });
    }
  }

  // Add this method to handle adding the current player to the game
  joinGame() {
    const username = this.authService.getUsername();
    if (!username) {
      alert('You must be logged in to join a game');
      return;
    }

    this.gameService.joinGame(this.gameId, username).subscribe({
      next: () => {
        this.loadGame();
      },
      error: (error) => {
        console.error('Error joining game:', error);
        alert(error.error?.error || 'Failed to join game');
      }
    });
  }

  // Add method to check if current user is in the game
  isPlayerInGame(): boolean {
    if (!this.game || !this.currentUserId) return false;
    return this.game.players.some(p => p.userId === this.currentUserId);
  }

  // Add this method to get current user's player info
  getCurrentPlayerInfo(): Player | null {
    if (!this.game || !this.currentUserId) return null;
    return this.game.players.find(p => p.userId === this.currentUserId) || null;
  }

  editPlayerName(player: Player, event: Event) {
    event.stopPropagation();
    const newName = prompt('Enter new name for player:', player.name);
    if (newName && newName.trim() && newName !== player.name) {
      this.gameService.updatePlayerName(this.gameId, player.id, newName.trim()).subscribe({
        next: () => {
          this.loadGame();
        },
        error: (error) => {
          console.error('Error updating player name:', error);
          alert(error.error?.error || 'Failed to update player name');
        }
      });
    }
  }

  removePlayer(player: Player, event: Event) {
    event.stopPropagation();
    if (confirm(`Are you sure you want to remove ${player.name} from the game?`)) {
      this.gameService.leaveGame(this.gameId, player.id).subscribe({
        next: () => {
          this.loadGame();
        },
        error: (error) => {
          console.error('Error removing player:', error);
          alert(error.error?.error || 'Failed to remove player');
        }
      });
    }
  }
}