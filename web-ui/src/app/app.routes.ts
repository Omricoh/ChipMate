import { Routes } from '@angular/router';
import { HomeComponent } from './components/home/home.component';
import { LoginComponent } from './components/auth/login/login.component';
import { GameComponent } from './components/game/game.component';
import { CreateGameComponent } from './components/game/create-game/create-game.component';
import { JoinGameComponent } from './components/game/join-game/join-game.component';
import { AuthGuard } from './guards/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: '/home', pathMatch: 'full' },
  { path: 'home', component: HomeComponent },
  { path: 'login', component: LoginComponent },
  {
    path: 'create-game',
    component: CreateGameComponent,
    canActivate: [AuthGuard]
  },
  {
    path: 'join/:gameCode',
    component: JoinGameComponent
  },
  {
    path: 'game/:gameId',
    component: GameComponent,
    canActivate: [AuthGuard]
  },
  { path: '**', redirectTo: '/home' }
];