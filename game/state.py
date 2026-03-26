from game.config import EPISODES, get_ending
from game.character    import call_fon

MOOD_SCORE = {'warm': 1, 'touched': 2, 'neutral': 0, 'cold': -1}

ENDING_KEY_MAP = {
    ('WARM', 0): 'warm_a', ('WARM', 1): 'warm_b', ('WARM', 2): 'warm_c',
    ('COLD', 0): 'cold_a', ('COLD', 1): 'cold_b', ('COLD', 2): 'cold_c',
}

class GameState:
    def __init__(self):
        self.ap            = 20
        self.tp            = 20
        self.current_ep_id = 'EP1'
        self.mood_counter  = 0
        self.turn          = 0
        self.route         = None
        self.game_over     = False

    def current_ep(self):
        return EPISODES[self.current_ep_id]['data']

    def episode_label(self):
        return self.current_ep()['title']

    def _clamp_stats(self):
        self.ap = max(0, min(100, self.ap))
        self.tp = max(0, min(100, self.tp))

    def _is_branch_ep(self):
        return 'branch_by_mood' in EPISODES[self.current_ep_id]

    def _is_final_ep(self):
        ep = EPISODES[self.current_ep_id]
        return 'next' not in ep and 'branch_by_mood' not in ep

    def _resolve_branch(self):
        ep         = EPISODES[self.current_ep_id]
        branch_map = ep['branch_by_mood']
        if self.mood_counter > 0:
            next_ep = branch_map['warm_route']
            if self.route is None: self.route = 'WARM'
        else:
            next_ep = branch_map['cold_route']
            if self.route is None: self.route = 'COLD'
        self.mood_counter = 0
        return next_ep

    def _resolve_ending(self):
        from game.config import ENDINGS
        route  = self.route or 'COLD'
        pool   = ENDINGS[route]
        ending = get_ending(route, self.ap, self.tp)
        idx    = pool.index(ending)
        key    = ENDING_KEY_MAP.get((route, idx), 'cold_c')
        return {'ending_data': ending, 'ending_key': key}

    def process_turn(self, player_input: str) -> dict:
        if self.game_over:
            return {'error': 'game already ended'}

        ep_data    = self.current_ep()
        fon_result = call_fon(player_input, ep_data, self.ap, self.tp)

        self.ap += fon_result['ap_change']
        self.tp += fon_result['tp_change']
        self._clamp_stats()

        mood = fon_result['mood']
        self.mood_counter += MOOD_SCORE.get(mood, 0)
        self.turn += 1

        event      = None
        ending_key = None
        new_ep_narrative = None
        new_ep_context   = None
        new_ep_intro     = None
        new_ep_hint      = None

        if self.turn >= self.current_ep()['max_turns']:
            self.turn = 0
            if self._is_final_ep():
                self.game_over = True
                resolved       = self._resolve_ending()
                event          = 'ending'
                ending_key     = resolved['ending_key']
            elif self._is_branch_ep():
                self.current_ep_id = self._resolve_branch()
                event            = 'branch'
                new_ep_narrative = self.current_ep().get('narrative', '')
                new_ep_context   = self.current_ep().get('context', '')
                new_ep_intro     = self.current_ep().get('fon_intro', '')
                new_ep_hint      = self.current_ep().get('hint', '')
            else:
                self.current_ep_id = EPISODES[self.current_ep_id].get('next', self.current_ep_id)
                new_ep_narrative = self.current_ep().get('narrative', '')
                new_ep_context   = self.current_ep().get('context', '')
                new_ep_intro     = self.current_ep().get('fon_intro', '')
                new_ep_hint      = self.current_ep().get('hint', '')

        return {
            'reaction'       : fon_result['reaction'],
            'mood'           : mood,
            'reason'         : fon_result.get('reason', ''),
            'ap'             : self.ap,
            'tp'             : self.tp,
            'ap_change'      : fon_result['ap_change'],
            'tp_change'      : fon_result['tp_change'],
            'mood_counter'   : self.mood_counter,
            'episode'        : self.current_ep_id,
            'episode_label'  : self.episode_label(),
            'bg_prompt'      : self.current_ep().get('bg_prompt', ''),
            'event'          : event,
            'ending'         : ending_key,
            'new_ep_narrative': new_ep_narrative,
            'new_ep_context' : new_ep_context,
            'new_ep_intro'   : new_ep_intro,
            'new_ep_hint'    : new_ep_hint,
        }