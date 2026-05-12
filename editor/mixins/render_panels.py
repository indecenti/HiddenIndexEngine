"""
editor/mixins/render_panels.py

RenderPanelsMixin — rendering pannello sinistro (tree/catalog),
                    pannello destro (layers/props).
"""

import time
import pygame

from editor.constants import (
    TOP_BAR_H, STATUS_H,
    ACCENT, BORDER, BTN, BTN_AC, BTN_HO, PANEL,
    TXT, TXT_DIM, TXT_HI, OK_C, ERR_C, WARN_C, ALWAYS_C, FX_C,
    DEFAULT_LAYERS, UI_TIPS,
    layer_color,
)
from editor.core.io import _load_scene_data
from editor.ui.draw import (
    _txt, _draw_text, _rect, _button, _in_rect, _text_wh, _slider, _input_box, _scrollbar, _draw_shape_icon,
)


class RenderPanelsMixin:
    """Rendering pannelli sinistro e destro dell'editor."""

    # ─────────────────────────────────────────────────────────────────────────
    # PANNELLO SINISTRO
    # ─────────────────────────────────────────────────────────────────────────

    def _r_left(self, h):
        _rect(self.screen, PANEL,  (0, TOP_BAR_H, self.panel_l_w, h-STATUS_H-TOP_BAR_H))
        _rect(self.screen, BORDER, (0, TOP_BAR_H, self.panel_l_w, h-STATUS_H-TOP_BAR_H), 1)

        from editor.constants import TAB_TREE, TAB_CATALOG, TAB_EFFECTS
        tabs = [(TAB_TREE, self._TR("tab_scene")), (TAB_CATALOG, self._TR("tab_obj")), (TAB_EFFECTS, self._TR("tab_fx"))]
        tab_w = self.panel_l_w // 3
        mx, my_raw = pygame.mouse.get_pos()
        for i, (tid, lbl) in enumerate(tabs):
            tr = pygame.Rect(i * tab_w, TOP_BAR_H, tab_w, 30)
            is_active = (self.l_tab == tid)
            # Disabilita tab Scene e Obj se il layer attivo è quello degli effetti
            is_disabled = (self.active_layer == "effects" and tid in (TAB_TREE, TAB_CATALOG))
            
            hov = _in_rect((mx, my_raw), tr)
            if hov and not is_disabled: self.active_tooltip = self._TR(f"tip_tab_{tid}")
            
            if is_disabled:
                _rect(self.screen, (35, 35, 45), tr) # Colore più scuro per disabilitato
                _rect(self.screen, BORDER, tr, 1)
                col = TXT_DIM
            else:
                _rect(self.screen, BTN_AC if is_active else (BTN_HO if hov else BTN), tr)
                _rect(self.screen, BORDER, tr, 1)
                col = FX_C if (tid == TAB_EFFECTS and is_active) else TXT_HI
            
            s = _txt(lbl, "sm", col)
            self.screen.blit(s, (tr.centerx - s.get_width() // 2, tr.centery - s.get_height() // 2))

        pygame.draw.line(self.screen, BORDER,
                         (0, TOP_BAR_H+30), (self.panel_l_w, TOP_BAR_H+30))

        if self.l_tab == TAB_TREE:
            self._r_tree(h)
        elif self.l_tab == TAB_EFFECTS:
            self._r_effects_catalog(h)
        else:
            self._r_catalog(h)

    # ── Tree ─────────────────────────────────────────────────────────────────

    def _r_tree(self, h):
        clip = pygame.Rect(0, TOP_BAR_H+32, self.panel_l_w, h-STATUS_H-TOP_BAR_H-32)
        self.screen.set_clip(clip)
        y = TOP_BAR_H + 36 - self.tree_scroll * 28

        if not self.levels:
            s = _txt(self._TR("tree_no_levels"), "sm", TXT_DIM)
            self.screen.blit(s, (8, y+8))

        mx, my_raw = pygame.mouse.get_pos()
        for level in self.levels:
            lvl_id = level["id"]
            exp = self.tree_expanded.get(lvl_id, False)
            row = pygame.Rect(8, y, self.panel_l_w - 24, 26)
            hov = _in_rect((mx, my_raw), row)
            _rect(self.screen, BTN_HO if hov else BTN, row, radius=3)
            arrow = ">" if not exp else "V"
            
            # Recupero nome reale per il livello
            l_key = level.get("cfg", {}).get("name_key")
            lvl_name = self._TR(l_key) if l_key else lvl_id
            
            _draw_text(self.screen, f"{arrow} {lvl_name}", "sm", ACCENT,
                       14, y+5, self.panel_l_w-32)
            y += 28

            if exp:
                for sdir in level["scenes"]:
                    sd      = _load_scene_data(sdir)
                    has_bg  = (sdir / sd.get("background", "background.jpg")).exists()
                    has_obj = len(sd.get("objects", [])) > 0
                    icon_c  = OK_C if (has_bg and has_obj) else (WARN_C if (has_bg or has_obj) else ERR_C)
                    is_cur  = (self.scene_path == sdir)
                    srow    = pygame.Rect(24, y, self.panel_l_w-40, 22)
                    if is_cur:
                        _rect(self.screen, BTN_AC, srow, radius=3)
                    elif _in_rect((mx, my_raw), srow):
                        _rect(self.screen, BTN_HO, srow, radius=3)
                    pygame.draw.circle(self.screen, icon_c, (30, y+11), 3)
                    
                    # Recupero nome reale per la scena
                    s_key = sd.get("name_key")
                    scn_name = self._TR(s_key) if s_key else sdir.name
                    
                    _draw_text(self.screen, scn_name, "sm",
                               TXT_HI if is_cur else TXT, 44, y+3, self.panel_l_w-60)
                    y += 24

        self.screen.set_clip(None)

    # ── Catalog ──────────────────────────────────────────────────────────────

    # Tag esclusi dalla griglia chip (tecnici, dimensionali, geografici, varianti)
    # Restano nel JSON e nella ricerca testuale — sono solo nascosti dall'UI dei filtri.
    CHIP_TAG_HIDDEN: frozenset[str] = frozenset({
        # Dimensione/scala — non utili come filtro tematico
        "piccolo", "medio", "grande",
        # Varianti visive — stessa semantica dell'originale
        "variante", "isometrico", "rotto", "nero", "rosso",
        # Geografie troppo granulari (le macro-aree geografiche restano)
        "nordico", "nordamerica", "sudamerica", "europa",
        "francia", "germania", "spagna", "uk", "grecia",
        "svezia", "svizzera", "orientale", "caraibi", "centroamerica",
        # Tag tecnici interni
        "carta_individuale", "seme", "volante", "mouse", "tablet",
        "tastiera", "visore",
    })

    @staticmethod
    def _get_catalog_tags(catalog: list, min_count: int = 1) -> list[str]:
        """Ritorna i tag presenti nel catalogo con almeno min_count oggetti."""
        hidden = RenderPanelsMixin.CHIP_TAG_HIDDEN
        counts: dict[str, int] = {}
        for obj in catalog:
            for tag in obj.get("tags", []):
                if tag not in hidden:
                    counts[tag] = counts.get(tag, 0) + 1
        return [t for t, c in sorted(counts.items(), key=lambda x: -x[1]) if c >= min_count]

    def _r_catalog(self, h):
        self._catalog_item_hitboxes = [] # Reset ogni frame
        mx, my_raw = pygame.mouse.get_pos()
        active_tags = getattr(self, "catalog_tag_filters", set())

        # Configurazione layout premium
        MARGIN       = 12
        INNER_W      = self.panel_l_w - MARGIN * 2
        SEARCH_H     = 32
        SEARCH_Y     = TOP_BAR_H + 38
        
        is_searching = self.catalog_searching
        has_search_text = bool(self.catalog_search)
        search_r = pygame.Rect(MARGIN, SEARCH_Y, INNER_W, SEARCH_H)
        
        # 1. Barra di ricerca oggetti
        _input_box(self.screen, search_r, self.catalog_search, focused=is_searching, 
                  hint=self._TR("cat_search_placeholder"), icon="search", font="md")
        
        if has_search_text:
            X_SZ = 24
            search_x_r = pygame.Rect(search_r.right - X_SZ - 6, search_r.centery - X_SZ // 2, X_SZ, X_SZ)
            hov_x = _in_rect((mx, my_raw), search_x_r)
            if hov_x:
                pygame.draw.circle(self.screen, (60, 65, 85), search_x_r.center, X_SZ // 2)
            _draw_shape_icon(self.screen, search_x_r.inflate(-2, -2), "x", TXT_HI if hov_x else TXT_DIM)
            self._search_x_rect = search_x_r
        else:
            self._search_x_rect = None

        # 2. Mini searchbar per filtrare le categorie (Tag)
        TAG_SEARCH_H = 28
        tag_q = getattr(self, "catalog_tag_search", "").lower()
        is_tag_searching = getattr(self, "catalog_tag_searching", False)
        has_tag_text = bool(tag_q)
        tag_search_r = pygame.Rect(MARGIN, search_r.bottom + 8, INNER_W, TAG_SEARCH_H)
        
        _input_box(self.screen, tag_search_r, tag_q, focused=is_tag_searching, 
                  hint=self._TR("cat_tag_placeholder"), icon="tag", font="sm")
        
        if has_tag_text:
            X_SZ = 22
            tag_x_r = pygame.Rect(tag_search_r.right - X_SZ - 5, tag_search_r.centery - X_SZ // 2, X_SZ, X_SZ)
            hov_tx = _in_rect((mx, my_raw), tag_x_r)
            if hov_tx:
                pygame.draw.circle(self.screen, (55, 58, 75), tag_x_r.center, X_SZ // 2)
            _draw_shape_icon(self.screen, tag_x_r.inflate(-2, -2), "x", TXT_HI if hov_tx else TXT_DIM)
            self._tag_search_x_rect = tag_x_r
        else:
            self._tag_search_x_rect = None
            
        self._tag_search_rect = tag_search_r

        # 2.5 Filtro Stile (Dropdown Intelligente)
        STYLE_Y = tag_search_r.bottom + 8
        styles = ["tutti", "real", "line art", "cartoon"]
        current_st = getattr(self, "catalog_style_filter", "tutti")
        
        # Conteggio oggetti per stile
        st_counts = {"tutti": len(self.catalog), "real": 0, "line art": 0, "cartoon": 0}
        for c_item in self.catalog:
            st = c_item.get("style", "real")
            if st in st_counts: st_counts[st] += 1

        # Rettangolo del selettore
        sel_rect = pygame.Rect(MARGIN, STYLE_Y, INNER_W, 28)
        self._catalog_style_sel_rect = sel_rect # Esporta per input handler
        is_open = getattr(self, "catalog_style_open", False)
        
        # Hitbox per hover visivo
        h_sel = _in_rect((mx, my_raw), sel_rect)
            
        _button(self.screen, sel_rect, f"STILE: {current_st.upper()}", hovered=h_sel, active=is_open, font="sm")
        _draw_shape_icon(self.screen, (sel_rect.x + sel_rect.w - 25, sel_rect.y, 25, 28), "down" if not is_open else "up", TXT_HI)

        # --- Fine Griglia ---
        self.screen.set_clip(None)

        # 3. Chip Tag: box a dimensione fissa (scrollabile)
        CHIPS_TOP = STYLE_Y + 36
        TAG_BOX_H   = 196 
        CHIP_GAP_X  = 6
        CHIP_GAP_Y  = 6
        CHIP_H      = 26
        CHIP_COLS   = 2

        active_style = getattr(self, "catalog_style_filter", "real")
        
        # FIX: Filtriamo il catalogo per stile PRIMA di estrarre i tag suggeriti.
        # Se siamo in "tutti", mostriamo i tag più frequenti (min_count=2).
        # Se siamo in uno stile specifico, mostriamo TUTTI i tag pertinenti (min_count=1).
        style_filtered_pool = [
            c for c in self.catalog 
            if (active_style == "tutti" or c.get("style", "real") == active_style)
        ]
        
        m_count = 2 if active_style == "tutti" else 1
        top_tags = self._get_catalog_tags(style_filtered_pool, min_count=m_count)
        
        # Filtro categorie: cerca sia nel tag ID che nel tag tradotto (label)
        tag_items = []
        for t in top_tags:
            label = self._TR(f"tag_{t}", t.capitalize())
            if not tag_q or tag_q in label.lower() or tag_q in t.lower():
                tag_items.append((t, label))
        
        # Riordina: i tag attivi saltano in cima
        tag_items.sort(key=lambda x: x[0] not in active_tags)
        
        tag_clip = pygame.Rect(MARGIN, CHIPS_TOP, INNER_W, TAG_BOX_H)
        _rect(self.screen, (20, 21, 28), tag_clip, radius=6)
        _rect(self.screen, BORDER, tag_clip, 1, radius=6)
        
        self.screen.set_clip(tag_clip)
        col_w = (tag_clip.w - CHIP_GAP_X - 16) // CHIP_COLS
        
        # Voce "Tutti" (Pulsante speciale in cima)
        tutti_active = not active_tags
        tutti_r = pygame.Rect(tag_clip.x + 6, tag_clip.y + 6 - self.catalog_tags_scroll * (CHIP_H + CHIP_GAP_Y), 
                               tag_clip.w - 12, CHIP_H)
        
        if tutti_active:
            _rect(self.screen, ACCENT, tutti_r, radius=5)
            tcol = (15, 15, 25)
        else:
            _rect(self.screen, (40, 44, 58), tutti_r, radius=5)
            tcol = TXT_DIM

        ts = _txt(self._TR("cat_tag_all"), "sm", tcol)
        self.screen.blit(ts, (tutti_r.centerx - ts.get_width() // 2, tutti_r.centery - ts.get_height() // 2))
        
        # Registra "Tutti" solo se visibile nel clip
        self._catalog_chip_rects = []
        if tutti_r.bottom > tag_clip.y and tutti_r.top < tag_clip.bottom:
            self._catalog_chip_rects.append(("tutti", tutti_r))

        # Griglia categorie
        for idx, (tag_id, tag_label) in enumerate(tag_items):
            col = idx % CHIP_COLS
            row = idx // CHIP_COLS + 1
            cx = tag_clip.x + 6 + col * (col_w + CHIP_GAP_X)
            cy = tag_clip.y + 6 + row * (CHIP_H + CHIP_GAP_Y) - self.catalog_tags_scroll * (CHIP_H + CHIP_GAP_Y)
            
            chip_r = pygame.Rect(cx, cy, col_w, CHIP_H)
            if cy + CHIP_H < tag_clip.y or cy > tag_clip.bottom:
                continue 
                
            is_active = tag_id in active_tags
            hov = _in_rect((mx, my_raw), chip_r) and tag_clip.collidepoint(mx, my_raw)

            if is_active:
                _rect(self.screen, ACCENT, chip_r, radius=5)
                ccol = (15, 15, 25)
            elif hov:
                _rect(self.screen, (55, 60, 80), chip_r, radius=5)
                _rect(self.screen, TXT_HI, chip_r, 1, radius=5)
                ccol = TXT_HI
            else:
                _rect(self.screen, (35, 38, 50), chip_r, radius=5)
                ccol = TXT_DIM

            t_surf = _txt(tag_label, "sm", ccol)
            if t_surf.get_width() > col_w - 12:
                short = tag_label[:max(1, int(len(tag_label) * (col_w-18)/t_surf.get_width()))] + ".."
                t_surf = _txt(short, "sm", ccol)
            
            self.screen.blit(t_surf, (chip_r.x + 8, chip_r.centery - t_surf.get_height() // 2))
            self._catalog_chip_rects.append((tag_id, chip_r))

        self.screen.set_clip(None)
        
        # Scrollbar categorie (mini)
        total_rows = (len(tag_items) + CHIP_COLS - 1) // CHIP_COLS + 1
        visible_rows = TAG_BOX_H // (CHIP_H + CHIP_GAP_Y)
        max_tag_scroll = max(0, total_rows - visible_rows)
        self._tag_scroll_info = {"rect": tag_clip, "max": max_tag_scroll}
        
        if max_tag_scroll > 0:
            sb_x = tag_clip.right - 5
            _scrollbar(self.screen, sb_x, tag_clip.y + 6, 3, tag_clip.h - 12, 
                       self.catalog_tags_scroll, total_rows, visible_rows)

        # Separatore orizzontale (Sleek)
        sep_y = tag_clip.bottom + 12
        pygame.draw.line(self.screen, BORDER, (MARGIN, sep_y), (self.panel_l_w - MARGIN, sep_y))

        # ── 4. Lista oggetti (Pool catalogo) ──────────────────────────────────
        add_btn_h    = 36
        list_y_start = sep_y + 8
        available_h  = h - STATUS_H - list_y_start - add_btn_h
        item_h       = 74 

        clip = pygame.Rect(0, list_y_start, self.panel_l_w, available_h)
        self.screen.set_clip(clip)

        import unicodedata
        def normalize(s):
            return "".join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()

        q = self.catalog_search.lower().strip()
        q_norm = normalize(q.lstrip("#"))
        
        filtered = [
            c for c in style_filtered_pool 
            if (not active_tags or all(t in c.get("tags", []) for t in active_tags))
            and (
                not q or q in c["id"].lower() 
                or any(q_norm in normalize(t) for t in c.get("tags", []))
                or any(q_norm in normalize(self._TR(f"tag_{t}", t)) for t in c.get("tags", [])) 
                or any(q in str(self._lang_data.get(l,{}).get(c["label_key"],"")).lower() for l in self.LANGS)
            )
        ]
        if not filtered:
            txt = self._TR("cat_no_results") if (self.catalog_search or active_tags) else self._TR("cat_empty")
            _draw_text(self.screen, txt, "sm", (100, 105, 130), MARGIN + 4, list_y_start + 12)

        used_counts = {}
        for o in self.scene_data.get("objects", []):
            cid = o.get("catalog_id", "")
            used_counts[cid] = used_counts.get(cid, 0) + 1

        visible_items = max(1, available_h // (item_h + 2))

        for i, cat in enumerate(filtered):
            iy = list_y_start + i * (item_h + 4) - self.catalog_scroll * (item_h + 4)
            if iy + item_h < list_y_start or iy > h - STATUS_H - add_btn_h:
                continue
                
            r = pygame.Rect(MARGIN, iy, INNER_W - 16, item_h) # Offset per scrollbar
            cid = cat.get("id", "")
            is_sel = (self.catalog_sel == cid)
            hov = _in_rect((mx, my_raw), r) and not is_sel
            count = used_counts.get(cid, 0)
            
            # Animazione subtle su hover/select
            bg = BTN_AC if is_sel else ((42, 45, 60) if hov else ((32, 35, 45) if count > 0 else BTN))
            bcol = ACCENT if is_sel else (WARN_C if count > 0 else (TXT_DIM if not hov else TXT_HI))
            
            _rect(self.screen, bg, r, radius=6)
            _rect(self.screen, bcol, r, 2 if is_sel else 1, radius=6)

            # Thumbnail
            if self.game_path:
                rat = self._get_asset_ratio(cid)
                tw, th = (48, int(48 / rat)) if rat > 1.0 else (int(48 * rat), 48)
                ic = self._load_img(self.game_path / cat.get("icon", ""), (tw, th))
                if ic:
                    self.screen.blit(ic, (r.x + 8 + (48-tw)//2, r.y + (item_h-th)//2))

            # Info (Allineamento millimetrico)
            tx = r.x + 64
            tw_limit = r.w - 72
            
            _draw_text(self.screen, cid, "md", (240, 243, 255) if is_sel else TXT_HI, tx, r.y + 10, tw_limit)
            
            lkey = cat.get("label_key", f"obj_{cid}")
            localized_label = self._TR(lkey) if lkey else ""
            if localized_label:
                _draw_text(self.screen, localized_label, "sm", (140, 145, 170), tx, r.y + 30, tw_limit)

            tags = cat.get("tags", [])
            if tags:
                tstr = " ".join(f"#{self._TR(f'tag_{t}', t)}" for t in tags[:3])
                tcol = ACCENT if active_tags and any(t in active_tags for t in tags) else (90, 95, 125)
                _draw_text(self.screen, tstr, "sm", tcol, tx, r.y + 48, tw_limit)

            if count > 0:
                badge_r = pygame.Rect(r.right - 28, r.y + 8, 22, 16)
                _rect(self.screen, WARN_C, badge_r, radius=3)
                bs = _txt(str(count), "sm", (20, 20, 30))
                self.screen.blit(bs, (badge_r.centerx - bs.get_width()//2, badge_r.centery - bs.get_height()//2))

        self.screen.set_clip(None)
        
        # Info scorrimento e Hitbox (Esportazione per input_handlers)
        max_scr = max(0, len(filtered) - visible_items)
        self._catalog_scroll_info = {"y_start": list_y_start, "bar_h": available_h, "max_scroll": max_scr, "list_y": list_y_start}
        
        # Rigeneriamo la lista delle hitbox solo per gli elementi visibili (clippati correttamente)
        for i, cat in enumerate(filtered):
            iy = list_y_start + i * (item_h + 4) - self.catalog_scroll * (item_h + 4)
            if iy + item_h < list_y_start or iy > list_y_start + available_h:
                continue
            # Rect ASSOLUTO (screen-space)
            hr = pygame.Rect(MARGIN, iy, INNER_W - 16, item_h)
            self._catalog_item_hitboxes.append((cat["id"], hr))

        if max_scr > 0:
            _scrollbar(self.screen, self.panel_l_w - 12, list_y_start, 4, available_h, self.catalog_scroll, len(filtered), visible_items)

        # 5. Pulsante "Nuovo oggetto" (Fondo fisso)
        by = h - STATUS_H - add_btn_h + 3
        br = pygame.Rect(MARGIN, by, INNER_W, add_btn_h - 6)
        _button(self.screen, br, self._TR("cat_btn_add_asset"), _in_rect((mx, my_raw), br), font="md")

        # 6. OVERLAY DROPDOWN (Z-Order massimo: disegnato dopo tutto)
        if is_open:
            self._catalog_style_opt_rects = [] # Reset e popolamento
            for i, s in enumerate(styles):
                opt_r = pygame.Rect(sel_rect.x, sel_rect.y + 28 + (i * 26), sel_rect.w, 26)
                self._catalog_style_opt_rects.append((s, opt_r))
                
                h_opt = _in_rect((mx, my_raw), opt_r)
                bg_opt = (60, 65, 85) if h_opt else (35, 38, 50)
                if s == current_st: bg_opt = ACCENT
                
                _rect(self.screen, bg_opt, opt_r, radius=2)
                _rect(self.screen, (80, 80, 100), opt_r, 1, radius=2)
                
                count = st_counts.get(s, 0)
                label = f"{s.upper()} ({count})"
                t_col = (15, 15, 25) if (s == current_st or h_opt) else TXT_HI
                _draw_text(self.screen, label, "sm", t_col, opt_r.x + 12, opt_r.y + 6)

    # ── Effects Catalog ──────────────────────────────────────────────────────

    def _r_effects_catalog(self, h):
        """Pannello catalogo effetti visivi."""
        add_btn_h    = 32
        list_y_start = TOP_BAR_H + 36
        clip = pygame.Rect(0, list_y_start, self.panel_l_w,
                           h - STATUS_H - list_y_start - add_btn_h)
        self.screen.set_clip(clip)
        self._effects_item_hitboxes = [] # Reset ogni frame
        item_h = 64
        mx, my_raw = pygame.mouse.get_pos()

        effects = getattr(self, "effects_catalog", [])
        used_counts = {}
        for fx in self.scene_data.get("effects", []):
            eid = fx.get("effect_id", "")
            used_counts[eid] = used_counts.get(eid, 0) + 1

        if not effects:
            s = _txt(self._TR("fx_no_effects"), "sm", TXT_DIM)
            self.screen.blit(s, (8, list_y_start + 8))
            self.screen.set_clip(None)
            return

        import math as _math
        t = getattr(self, "_fx_editor_time", 0.0)

        for i, fx_cat in enumerate(effects):
            iy = list_y_start + 4 + i * (item_h + 2) - self.effects_catalog_scroll * (item_h + 2)
            if iy + item_h < list_y_start or iy > h - STATUS_H - add_btn_h:
                continue
            MARGIN = 12
            r = pygame.Rect(MARGIN, iy, self.panel_l_w - MARGIN - 24, item_h)
            self._effects_item_hitboxes.append((fx_cat.get("id", ""), r))
            eid    = fx_cat.get("id", "")
            ftype  = fx_cat.get("type", "")
            is_sel = (self.effects_catalog_sel == eid)
            hov    = _in_rect((mx, my_raw), r) and not is_sel
            count  = used_counts.get(eid, 0)
            is_used = count > 0
            bg_col   = BTN_AC if is_sel else (BTN_HO if hov else ((35, 38, 48) if is_used else BTN))
            border_c = FX_C if is_sel else (WARN_C if is_used else (TXT_HI if hov else BORDER))
            _rect(self.screen, bg_col, r, radius=4)
            _rect(self.screen, border_c, r, 1 if not is_sel else 2, radius=4)

            # --- ANTEPRIME SPECIFICHE (ICONE DINAMICHE) ---
            icon_cx, icon_cy = r.x + 24, iy + item_h // 2
            def_col = fx_cat.get("default_color", [255, 215, 60])
            pulse = (_math.sin(t * 4.0 + i) + 1) * 0.5
            
            if ftype == "bubble_tip":
                # Icona Fumetto
                bw, bh = 14, 10
                pygame.draw.rect(self.screen, (240, 240, 255), (icon_cx - bw//2, icon_cy - bh//2 - 2, bw, bh), border_radius=3)
                pygame.draw.polygon(self.screen, (240, 240, 255), [(icon_cx, icon_cy+bh//2-1), (icon_cx-3, icon_cy+bh//2+3), (icon_cx+3, icon_cy+bh//2-1)])
            elif ftype == "flies":
                # Icona Sciame (pixel vibranti)
                for fidx in range(5):
                    fx_off = _math.sin(t * 15.0 + fidx) * 6
                    fy_off = _math.cos(t * 12.0 + fidx * 1.5) * 6
                    pygame.draw.rect(self.screen, (50, 50, 50), (icon_cx + fx_off, icon_cy + fy_off, 2, 2))
            elif ftype == "smoke":
                # Icona Fumo (micro cloud)
                for sidx in range(3):
                    sy_off = -pulse * 8 + sidx * 4
                    sa = int(100 * (1.0 - pulse))
                    pygame.draw.circle(self.screen, (150, 150, 160, sa), (icon_cx, icon_cy + sy_off), 5 + sidx*2)
            else:
                # Icona Bagliore Default
                glow_r = int(6 + pulse * 4)
                bright_col = tuple(min(255, int(c * (0.7 + pulse * 0.3))) for c in def_col)
                pygame.draw.circle(self.screen, (*bright_col, 80), (icon_cx, icon_cy), glow_r + 4)
                pygame.draw.circle(self.screen, bright_col, (icon_cx, icon_cy), glow_r // 2)

            # Testo (3 righe ben spaziate)
            _draw_text(self.screen, fx_cat.get("label", eid), "sm",
                       TXT_HI if not is_used else (200, 200, 220), r.x + 52, iy + 6, self.panel_l_w - 80)
            _draw_text(self.screen, ftype.upper(), "sm",
                       FX_C if is_sel else (80, 120, 160), r.x + 52, iy + 24, self.panel_l_w - 80)
            
            dr = fx_cat.get("default_radius", 50)
            di = fx_cat.get("default_intensity", 1.0)
            val_info = f"Default: r={dr}  i={di}"
            _draw_text(self.screen, val_info, "sm", TXT_DIM, r.x + 52, iy + 40, self.panel_l_w - 80)

            if is_used:
                pygame.draw.circle(self.screen, WARN_C, (r.right - 12, iy + 12), 4)
                if count > 1:
                    _draw_text(self.screen, f"x{count}", "sm", WARN_C, r.right - 35, iy + 8)

        self.screen.set_clip(None)

        # Info placeholder (no "Nuovo Effetto" button - il catalogo è fisso)
        by  = h - STATUS_H - add_btn_h + 2
        MARGIN = 8
        hint_r = pygame.Rect(MARGIN, by, self.panel_l_w - MARGIN - 24, add_btn_h - 4)
        _rect(self.screen, BTN, hint_r, radius=4)
        _rect(self.screen, BORDER, hint_r, 1, radius=4)
        hs = _txt(self._TR("fx_hint_click"), "sm", TXT_DIM)
        self.screen.blit(hs, (hint_r.centerx - hs.get_width() // 2,
                               hint_r.centery - hs.get_height() // 2))

    # ─────────────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    # PANNELLO DESTRO
    # ─────────────────────────────────────────────────────────────────────────

    def _r_right(self, w, h):
        rx0 = w - self.panel_r_w
        _rect(self.screen, PANEL,  (rx0, TOP_BAR_H, self.panel_r_w, h-STATUS_H-TOP_BAR_H))
        _rect(self.screen, BORDER, (rx0, TOP_BAR_H, self.panel_r_w, h-STATUS_H-TOP_BAR_H), 1)

        from editor.constants import TAB_LAYERS, TAB_PROPS
        mx, my_raw = pygame.mouse.get_pos()
        for i, (tid, lbl) in enumerate([(TAB_LAYERS, self._TR("tab_layers")), (TAB_PROPS, self._TR("tab_props"))]):
            tr = pygame.Rect(rx0 + i*(self.panel_r_w//2), TOP_BAR_H, self.panel_r_w//2, 30)
            hov = _in_rect((mx, my_raw), tr)
            if hov: self.active_tooltip = self._TR(f"tip_tab_{tid}")
            
            bg = BTN_AC if self.r_tab==tid else (BTN_HO if hov else BTN)
            _rect(self.screen, bg, tr)
            _rect(self.screen, BORDER, tr, 1)
            s = _txt(lbl, "sm", TXT_HI)
            self.screen.blit(s, (tr.centerx-s.get_width()//2, tr.centery-s.get_height()//2))

        pygame.draw.line(self.screen, BORDER, (rx0, TOP_BAR_H+30), (w, TOP_BAR_H+30))

        if self.r_tab == TAB_LAYERS:
            self._r_layers(rx0, h)
        else:
            self._r_props(rx0, h)

    def _get_all_layers(self):
        layers = []
        for lyr in DEFAULT_LAYERS:
            # Converte 'objects_low' -> 'layer_low'
            key = "layer_" + lyr["id"].replace("objects_", "")
            layers.append({"id": lyr["id"], "z": lyr["z"], "label": self._TR(key)})
            
        layers.append({"id": "scene_global", "z": 0, "label": self._TR("layers_scene_global"), "is_scene": True})
        layers.append({"id": "effects", "z": 100, "label": self._TR("layers_all_effects"), "is_fx": True})
        return sorted(layers, key=lambda l: l["z"], reverse=True)

    def _r_layers(self, rx0, h):
        y = TOP_BAR_H + 36
        for lbl, lx in [(self._TR("tab_layers"), 8), (self._TR("layers_label_vis"), self.panel_r_w-82), (self._TR("layers_label_lock"), self.panel_r_w-52)]:
            self.screen.blit(_txt(lbl, "sm", TXT_DIM), (rx0+lx, y))
        y += 18
        pygame.draw.line(self.screen, BORDER, (rx0, y), (rx0+self.panel_r_w, y))
        y += 4

        mx, my_raw = pygame.mouse.get_pos()
        for layer in self._get_all_layers():
            lid, is_fx, is_scn = layer["id"], layer.get("is_fx"), layer.get("is_scene")
            is_act = (self.active_layer == lid)
            if is_scn: is_act = (self.selected_idx is None and getattr(self, "sel_effect_idx", None) is None)
            
            row_h, row = 40, pygame.Rect(rx0 + 8, y, self.panel_r_w - 24, 40)
            hov = _in_rect((mx, my_raw), row)
            _rect(self.screen, BTN_AC if is_act else (BTN_HO if hov else BTN), row, radius=5)
            
            if is_act:
                _rect(self.screen, ACCENT, row, 1, radius=5)
                self.screen.blit(_txt(">", "sm", TXT_HI), (rx0+8, y+12))
            
            lc = (100, 100, 120) if is_scn else ((255,180,50) if is_fx else layer_color(lid))
            if is_scn: pygame.draw.rect(self.screen, lc, (rx0 + 24, y + 14, 12, 12), border_radius=2)
            else: pygame.draw.circle(self.screen, lc, (rx0 + 30, y + 20), 6)
            
            vis = self.layer_vis.get(lid, True)
            cnt = sum(1 for o in self.scene_data.get("objects", []) if o.get("layer") == lid)
            txt_s = f"{layer['label']} {'[FX]' if is_fx else ('' if is_scn else f'({cnt})')}"
            _draw_text(self.screen, txt_s, "sm", TXT_HI if vis else TXT_DIM, rx0+42, y+12, self.panel_r_w-125)

            if not is_scn:
                # Occhio
                er = pygame.Rect(rx0+self.panel_r_w-80, y+8, 24, 24)
                ecol = (TXT_HI if vis else TXT_DIM) if not _in_rect((mx, my_raw), er) else ACCENT
                if _in_rect((mx, my_raw), er): self.active_tooltip = self._TR("tip_layer_visible")
                _draw_shape_icon(self.screen, er.inflate(0, -6), "eye_visible" if vis else "eye_hidden", ecol)

                # Lucchetto
                if not is_fx:
                    lr = pygame.Rect(rx0+self.panel_r_w-50, y+8, 24, 24)
                    lkd = self.layer_locked.get(lid, False)
                    lcol = (WARN_C if lkd else TXT_DIM) if not _in_rect((mx, my_raw), lr) else ACCENT
                    if _in_rect((mx, my_raw), lr): self.active_tooltip = self._TR("tip_layer_locked")
                    _draw_shape_icon(self.screen, lr, "lock_closed" if lkd else "lock_open", lcol)
            y += row_h + 4

        y += 8
        pygame.draw.line(self.screen, BORDER, (rx0, y), (rx0+self.panel_r_w, y))
        y += 10
        total = len(self.scene_data.get("objects", []))
        self.screen.blit(_txt(self._TR("cat_total_pool").format(total), "sm", TXT_DIM), (rx0+8, y))


    # ── Props ─────────────────────────────────────────────────────────────────

    def _set_hbox_scene(self, key, x, y_draw, w_b, h_b):
        y_virt = y_draw + self.prop_scroll - TOP_BAR_H
        self._scene_props_hitboxes[key] = pygame.Rect(x, y_virt, w_b, h_b)

    def _set_hbox_obj(self, key, x, y_draw, w_b, h_b):
        y_virt = y_draw + self.prop_scroll - TOP_BAR_H
        self._obj_props_hitboxes[key] = pygame.Rect(x, y_virt, w_b, h_b)

    def _set_hbox_fx(self, key, x, y_draw, w_b, h_b):
        y_virt = y_draw + self.prop_scroll - TOP_BAR_H
        self._fx_props_hitboxes[key] = pygame.Rect(x, y_virt, w_b, h_b)

    def _r_props(self, rx0, h):
        list_y_start = TOP_BAR_H + 36
        clip = pygame.Rect(rx0, list_y_start, self.panel_r_w, h - STATUS_H - list_y_start)
        self.screen.set_clip(clip)
        
        y = list_y_start - self.prop_scroll
        mx, my_raw = pygame.mouse.get_pos()

        # ── Proprietà Effetto ─────────────────────────────────────────────────
        effects = self.scene_data.get("effects", [])
        has_fx_sel = (getattr(self, "sel_effect_idx", None) is not None and self.sel_effect_idx < len(effects))
        has_obj_sel = (self.selected_idx is not None and self.selected_idx < len(self.scene_data.get("objects", [])))

        if has_fx_sel:
            self._fx_props_hitboxes = {}
            # Pulsante "Torna alla Scena" rapido
            back_r = pygame.Rect(rx0+4, y, self.panel_r_w-8, 26)
            hov_back = _in_rect((mx, my_raw), back_r)
            _button(self.screen, back_r, self._TR("prop_back_to_scene"), hov_back, font="sm")
            self._set_hbox_fx("back_btn", 4, y, self.panel_r_w-8, 26)
            y += 36
            self._r_effect_props(rx0, h, self.sel_effect_idx, y)
            return

        if not has_fx_sel and not has_obj_sel:
            # ── Proprietà Scena ───────────────────────────────────────────────
            self._scene_props_hitboxes = {}
            hdr = _txt(self._TR("prop_scene_hdr"), "sm", TXT_DIM)
            self.screen.blit(hdr, (rx0+8, y)); y += 20
            pygame.draw.line(self.screen, BORDER, (rx0, y), (rx0+self.panel_r_w, y)); y += 8

            if not self.scene_path:
                s = _txt(self._TR("prop_no_scene"), "sm", TXT_DIM)
                self.screen.blit(s, (rx0+8, y)); return

            # ID
            s = _txt(self._TR("prop_id"), "sm", TXT_DIM)
            self.screen.blit(s, (rx0+8, y))
            sv = _txt(self.scene_data.get("id", self.scene_path.name), "sm", TXT_HI)
            self.screen.blit(sv, (rx0+140, y)); y += 24

            # Background
            bg_name = self.scene_data.get("background", "background.jpg")
            s = _txt(self._TR("prop_background"), "sm", TXT_DIM)
            self.screen.blit(s, (rx0+8, y)); y += 20
            _draw_text(self.screen, bg_name, "sm", TXT, rx0+8, y, self.panel_r_w-16); y += 20
            if self.bg_surf:
                tw = self.panel_r_w - 16
                th = int(tw * 9/16)
                tc = self._load_img(self.scene_path / bg_name, (tw, th))
                if tc:
                    self.screen.blit(tc, (rx0+8, y))
                    _rect(self.screen, BORDER, (rx0+8, y, tw, th), 1)
                y += th + 4
            btn_r = pygame.Rect(rx0+4, y, self.panel_r_w-8, 26)
            _button(self.screen, btn_r, self._TR("prop_btn_choose_bg"), _in_rect((mx, my_raw), btn_r))
            self._set_hbox_scene("bg_btn", 4, y, self.panel_r_w-8, 26)
            y += 32

            y += 4


            # Rotazione Automatica
            auto_r = self.scene_data.get("auto_random_finds", False)
            btn_r_auto = pygame.Rect(rx0+4, y, self.panel_r_w-8, 28)
            hov_auto = _in_rect((mx, my_raw), btn_r_auto)
            _rect(self.screen, (30, 60, 40) if auto_r else BTN, btn_r_auto, radius=4)
            _rect(self.screen, OK_C if auto_r else BORDER, btn_r_auto, 1 if not hov_auto else 2, radius=4)
            label_auto = ("ON - " if auto_r else "OFF - ") + self._TR("prop_auto_random")
            _draw_text(self.screen, label_auto, "sm", OK_C if auto_r else TXT_DIM, rx0+12, y+6)
            self._set_hbox_scene("auto_btn", 4, y, self.panel_r_w-8, 28)
            y += 34

            # Selezione Layer Casuale (NEW)
            rand_l = self.scene_data.get("random_layer_selection", False)
            btn_r_rand = pygame.Rect(rx0+4, y, self.panel_r_w-8, 28)
            hov_rand = _in_rect((mx, my_raw), btn_r_rand)
            _rect(self.screen, (60, 40, 60) if rand_l else BTN, btn_r_rand, radius=4)
            _rect(self.screen, ALWAYS_C if rand_l else BORDER, btn_r_rand, 1 if not hov_rand else 2, radius=4)
            label_rand = ("ON - " if rand_l else "OFF - ") + self._TR("prop_random_layer")
            _draw_text(self.screen, label_rand, "sm", ALWAYS_C if rand_l else TXT_DIM, rx0+12, y+6)
            self._set_hbox_scene("rand_l_btn", 4, y, self.panel_r_w-8, 28)
            y += 34

            if auto_r:
                s = _txt(self._TR("prop_find_qty"), "sm", ALWAYS_C); self.screen.blit(s, (rx0+8, y))
                y += 28 # Incrementato (era 21)
                n_random = self.scene_data.get("num_random_finds", 1)
                box_r_nr = (rx0+8, y-1, 65, 20)
                is_f_nr = (getattr(self, "_editing_prop", None) == ('scene', 0, 'num_random_finds'))
                _input_box(self.screen, box_r_nr, self._prop_buf if is_f_nr else str(n_random), is_f_nr)
                self._set_hbox_scene("nr_box", 8, y-1, 65, 20)
                
                slider_r_nr = (rx0+85, y-1, self.panel_r_w-93, 20)
                _slider(self.screen, slider_r_nr, n_random, 1, len(self.scene_data.get("objects", [])))
                self._set_hbox_scene("nr_slider", 85, y-1, self.panel_r_w-93, 20)
                y += 32

            y += 4
            pygame.draw.line(self.screen, BORDER, (rx0, y), (rx0+self.panel_r_w, y)); y += 8
            hdr2 = _txt(self._TR("prop_languages"), "sm", TXT_DIM)
            self.screen.blit(hdr2, (rx0+8, y)); y += 20
            lang_r = pygame.Rect(rx0+4, y, self.panel_r_w-8, 28)
            _button(self.screen, lang_r, self._TR("prop_btn_edit_translations"),
                    _in_rect((mx, my_raw), lang_r), active=self._lang_modal)
            self._set_hbox_scene("lang_btn", 4, y, self.panel_r_w-8, 28)
            y += 36

            pygame.draw.line(self.screen, BORDER, (rx0, y), (rx0+self.panel_r_w, y)); y += 8
            hdr3 = _txt(self._TR("prop_canvas_icons"), "sm", TXT_DIM)
            self.screen.blit(hdr3, (rx0+8, y)); y += 20
            ico_r  = pygame.Rect(rx0+4, y, self.panel_r_w-8, 26)
            lbl_ico = ("ON - " if self.show_icons else "OFF - ") + self._TR("prop_show_png")
            _button(self.screen, ico_r, lbl_ico,
                    _in_rect((mx, my_raw), ico_r), active=self.show_icons)
            self._set_hbox_scene("ico_btn", 4, y, self.panel_r_w-8, 26)
            y += 34

            # --- EFFETTO TORCIA (FLASHLIGHT) ---
            pygame.draw.line(self.screen, BORDER, (rx0, y), (rx0+self.panel_r_w, y)); y += 8
            hdr5 = _txt(self._TR("prop_flashlight_hdr"), "sm", FX_C)
            self.screen.blit(hdr5, (rx0+8, y)); y += 20
            
            flashlight = self.scene_data.get("flashlight", False)
            fl_btn_r = pygame.Rect(rx0+4, y, self.panel_r_w-8, 28)
            hov_fl = _in_rect((mx, my_raw), fl_btn_r)
            
            # Stile pulsante toggle
            fl_bg = (30, 45, 60) if flashlight else (40, 40, 45)
            _rect(self.screen, fl_bg, fl_btn_r, radius=4)
            _rect(self.screen, FX_C if flashlight else BORDER, fl_btn_r, 1 if not hov_fl else 2, radius=4)
            label_fl = (self._TR("prop_flashlight_on") if flashlight else self._TR("prop_flashlight_off"))
            _draw_text(self.screen, label_fl, "sm", FX_C if flashlight else TXT_DIM, rx0+12, y+6)
            self._set_hbox_scene("fl_btn", 4, y, self.panel_r_w-8, 28)
            y += 34
            
            if flashlight:
                s = _txt(self._TR("prop_light_radius"), "sm", TXT_DIM); self.screen.blit(s, (rx0+8, y))
                y += 28 # Incrementato (era 21)
                fl_rad = self.scene_data.get("flashlight_radius", 150.0)
                box_r_fl = pygame.Rect(rx0+8, y-1, 65, 20)
                is_f_fl = (getattr(self, "_editing_prop", None) == ('scene', 0, 'flashlight_radius'))
                _input_box(self.screen, box_r_fl, self._prop_buf if is_f_fl else f"{fl_rad:.1f}", is_f_fl)
                self._set_hbox_scene("fl_rad_box", 8, y-1, 65, 20)
                
                slider_r_fl = pygame.Rect(rx0+85, y-1, self.panel_r_w-93, 20)
                _slider(self.screen, slider_r_fl, fl_rad, 50, 500)
                self._set_hbox_scene("fl_rad_slider", 85, y-1, self.panel_r_w-93, 20)
                y += 32

            y += 6
            pygame.draw.line(self.screen, BORDER, (rx0, y), (rx0+self.panel_r_w, y)); y += 8
            save_r = pygame.Rect(rx0+4, y, self.panel_r_w-8, 28)
            _button(self.screen, save_r, self._TR("prop_btn_save_scene"),
                    _in_rect((mx, my_raw), save_r), active=self.scene_dirty, icon="save", center_text=True)
            self._set_hbox_scene("save_btn", 4, y, self.panel_r_w-8, 28)

            y += 34
            pygame.draw.line(self.screen, BORDER, (rx0, y), (rx0+self.panel_r_w, y)); y += 8
            hdr4 = _txt(self._TR("prop_music_hdr"), "sm", TXT_DIM)
            self.screen.blit(hdr4, (rx0+8, y)); y += 20
            music_list = self.scene_data.get("music", [])
            if not music_list:
                _draw_text(self.screen, self._TR("prop_no_music"), "sm", TXT_DIM, rx0+8, y)
                y += 20
            else:
                for m in music_list:
                    # Rimosso ♪ per pulizia visiva richiesta
                    _draw_text(self.screen, m, "sm", OK_C, rx0+8, y, self.panel_r_w-40)
                    y += 20
            y += 4
            mus_btn_r = pygame.Rect(rx0+4, y, self.panel_r_w-8, 26)
            _button(self.screen, mus_btn_r, self._TR("prop_btn_add_music"),
                    _in_rect((mx, my_raw), mus_btn_r))
            self._set_hbox_scene("mus_add_btn", 4, y, self.panel_r_w-8, 26)
            y += 30
            clr_btn_r = pygame.Rect(rx0+4, y, self.panel_r_w-8, 26)
            _button(self.screen, clr_btn_r, self._TR("prop_btn_clear_music"),
                    _in_rect((mx, my_raw), clr_btn_r), danger=True)
            self._set_hbox_scene("mus_clr_btn", 4, y, self.panel_r_w-8, 26)
            y += 34
            # Svuota Scena
            # Svuota Scena
            clear_scene_r = pygame.Rect(rx0+4, y, self.panel_r_w-8, 28)
            confirming = getattr(self, "_confirm_clear", False)
            btn_label = self._TR("prop_btn_clear_scene") if not confirming else self._TR("prop_confirm_clear")
            _button(self.screen, clear_scene_r, btn_label, 
                    _in_rect((mx, my_raw), clear_scene_r), danger=True, active=confirming)
            self._set_hbox_scene("clear_scene_btn", 4, y, self.panel_r_w-8, 28)
            
            # Fine clipping e disegno scrollbar props
            self.screen.set_clip(None)
            total_h = 1000 # Stima o calcola dinamicamente se possibile
            visible_h = h - STATUS_H - list_y_start
            _scrollbar(self.screen, rx0 + self.panel_r_w - 6, list_y_start, 4, visible_h,
                       self.prop_scroll, total_h, visible_h)
            return

        # ── Proprietà Oggetto ─────────────────────────────────────────────────
        self._obj_props_hitboxes = {}
        obj    = self.scene_data["objects"][self.selected_idx]
        cat_id = obj.get("catalog_id", "?")
        cat_e  = next((c for c in self.catalog if c["id"] == cat_id), None)
        mx, my_raw = pygame.mouse.get_pos()

        # Pulsante "Torna alla Scena"
        back_r = pygame.Rect(rx0+4, y, self.panel_r_w-8, 26)
        hov_back = _in_rect((mx, my_raw), back_r)
        _button(self.screen, back_r, self._TR("prop_back_to_scene"), hov_back, font="sm")
        self._set_hbox_obj("back_btn", 4, y, self.panel_r_w-8, 26)
        y += 40

        # Intestazione e Icona
        icon_drawn = False
        if cat_e and self.game_path:
            ic = self._load_img(self.game_path / cat_e.get("icon", ""), (38, 38))
            if ic:
                self.screen.blit(ic, (rx0+12, y))
                icon_drawn = True
        
        _draw_text(self.screen, cat_id.upper(), "md", TXT_HI, rx0+(55 if icon_drawn else 12), y+10, self.panel_r_w-70)
        y += 54
        pygame.draw.line(self.screen, BORDER, (rx0+8, y), (rx0+self.panel_r_w-8, y))
        y += 16

        # Layer di appartenenza
        lyr_id = obj.get("layer", "objects_mid")
        lyr_lbl = next((l["label"] for l in DEFAULT_LAYERS if l["id"] == lyr_id), lyr_id)
        _draw_text(self.screen, self._TR("prop_layer_label"), "sm", TXT_DIM, rx0+12, y)
        lsv = _txt(lyr_lbl, "sm", layer_color(lyr_id))
        self.screen.blit(lsv, (rx0 + self.panel_r_w - lsv.get_width() - 16, y))
        y += 24
        
        # Coordinate e Dimensioni
        dt = obj.get("detection_type", "circle")
        fields = [(self._TR("prop_coord_x"), round(obj.get("x", 0))), (self._TR("prop_coord_y"), round(obj.get("y", 0)))]
        if dt == "circle":
            fields.append((self._TR("prop_radius"), round(obj.get("radius", 30))))
        else:
            fields.append((self._TR("prop_width"), round(obj.get("width", 60))))
            fields.append((self._TR("prop_height"), round(obj.get("height", 60))))
        
        for lbl, val in fields:
            _draw_text(self.screen, lbl, "sm", TXT_DIM, rx0+12, y)
            sv = _txt(str(val), "mono", TXT_HI)
            self.screen.blit(sv, (rx0 + self.panel_r_w - sv.get_width() - 16, y))
            y += 24
        
        y += 12
        pygame.draw.line(self.screen, BORDER, (rx0+12, y), (rx0+self.panel_r_w-12, y))
        y += 16

        # Sezione Filtri (Grayscale)
        gs_active = obj.get("grayscale", False)
        if gs_active:
            gs_f = obj.get("grayscale_factor", 1.0)
            _draw_text(self.screen, self._TR("prop_bw_intensity"), "sm", TXT_DIM, rx0+12, y)
            y += 28
            
            box_w = 60
            box_r = pygame.Rect(rx0+12, y, box_w, 22)
            is_f = (getattr(self, "_editing_prop", None) == ('object', self.selected_idx, 'grayscale_factor'))
            _input_box(self.screen, box_r, self._prop_buf if is_f else str(int(gs_f*100)), is_f)
            self._set_hbox_obj("gs_box", 12, y, box_w, 22)
            
            sl_x, sl_w = rx0 + 12 + box_w + 10, self.panel_r_w - (box_w + 36)
            sl_rect = (sl_x, y+1, sl_w, 20)
            _slider(self.screen, sl_rect, gs_f, 0, 1, color=ACCENT)
            self._set_hbox_obj("gs_slider", 12 + box_w + 10, y+1, sl_w, 20)
            y += 42

        # Logica Oggetto (Fisso/Goal/Hint)
        is_auto = self.scene_data.get("auto_random_finds", False)
        
        # 1. Sempre Visibile (Fisso) - Solo se auto_random è ON
        if is_auto:
            is_fix = obj.get("always_show", False)
            btn_r = pygame.Rect(rx0+8, y, self.panel_r_w-16, 28)
            hov = _in_rect((mx, my_raw), btn_r)
            bg_c = (70, 55, 30) if is_fix else (40, 42, 50)
            _rect(self.screen, bg_c, btn_r, radius=5)
            _rect(self.screen, (ALWAYS_C if is_fix else BORDER), btn_r, 2 if hov else 1, radius=5)
            _draw_text(self.screen, self._TR("prop_fixed_goal"), "sm", ALWAYS_C if is_fix else TXT_HI, rx0+20, y+6)
            self._set_hbox_obj("always_btn", 8, y, self.panel_r_w-16, 28)
            y += 36

        # 3. Goal Toggle
        if not is_auto:
            is_goal = obj.get("is_goal", True)
            btn_g = pygame.Rect(rx0+8, y, self.panel_r_w-16, 28)
            hov_g = _in_rect((mx, my_raw), btn_g)
            bg_g = (30, 55, 40) if is_goal else (55, 35, 35)
            _rect(self.screen, bg_g, btn_g, radius=5)
            _rect(self.screen, (OK_C if is_goal else ERR_C), btn_g, 2 if hov_g else 1, radius=5)
            g_lbl = self._TR("prop_goal_find") if is_goal else self._TR("prop_goal_decor")
            _draw_text(self.screen, g_lbl, "sm", TXT_HI, rx0+20, y+6)
            self._set_hbox_obj("goal_btn", 8, y, self.panel_r_w-16, 28)
            y += 46

        # --- MINIGAME TRIGGER ---
        pygame.draw.line(self.screen, BORDER, (rx0 + 12, y), (rx0+self.panel_r_w - 12, y))
        y += 16
        _draw_text(self.screen, self._TR("prop_minigame_hdr"), "sm", ACCENT, rx0+12, y); y += 22
        
        m_trigger = obj.get("minigame_trigger")
        btn_m = pygame.Rect(rx0+8, y, self.panel_r_w-16, 28)
        hov_m = _in_rect((mx, my_raw), btn_m)
        
        bg_m = (30, 45, 60) if m_trigger else BTN
        _rect(self.screen, bg_m, btn_m, radius=5)
        _rect(self.screen, (ACCENT if m_trigger else BORDER), btn_m, 2 if hov_m else 1, radius=5)
        
        m_lbl = self._TR("prop_minigame_label").format(m_trigger['minigame_id'].upper()) if m_trigger else self._TR("prop_no_minigame")
        _draw_text(self.screen, m_lbl, "sm", TXT_HI if m_trigger else TXT_DIM, rx0+20, y+6)
        self._set_hbox_obj("minigame_btn", 8, y, self.panel_r_w-16, 28)
        y += 34
        
        if m_trigger:
            clr_m_r = pygame.Rect(rx0+8, y, self.panel_r_w-16, 26)
            if _button(self.screen, clr_m_r, self._TR("prop_btn_remove_trigger"), _in_rect((mx, my_raw), clr_m_r), danger=True):
                pass
            self._set_hbox_obj("minigame_clear_btn", 8, y, self.panel_r_w-16, 26)
            y += 32

        y += 10
        pygame.draw.line(self.screen, BORDER, (rx0 + 12, y), (rx0+self.panel_r_w - 12, y))
        y += 16

        # Azioni Finali (Duplica / Elimina)
        half = (self.panel_r_w - 24) // 2
        dup_r = pygame.Rect(rx0 + 12, y, half, 30)
        del_r = pygame.Rect(rx0 + 12 + half + 6, y, half, 30)
        
        hov_dup = _in_rect((mx, my_raw), dup_r)
        hov_del = _in_rect((mx, my_raw), del_r)
        
        _button(self.screen, dup_r, self._TR("prop_btn_duplicate"), hov_dup)
        _button(self.screen, del_r, self._TR("prop_btn_delete"), hov_del, danger=True)
        
        self._set_hbox_obj("dup_btn", 12, y, half, 30)
        self._set_hbox_obj("del_btn", 12 + half + 6, y, half, 30)
        y += 44

        # Scorciatoie veloci
        y += 8
        s_keys = [
            ("R", self._TR("shortcut_rotate")), ("Shift+R", self._TR("shortcut_rotate_ccw")),
            ("H / V", self._TR("shortcut_flip")), ("Ctrl+1-4", self._TR("shortcut_move_layer"))
        ]
        for k, a in s_keys:
            _draw_text(self.screen, f"{k}:", "xs", (120, 125, 140), rx0+12, y)
            _draw_text(self.screen, a, "xs", TXT_DIM, rx0+80, y)
            y += 16

        # Fine clipping e disegno scrollbar props
        self.screen.set_clip(None)
        total_h = y + self.prop_scroll - list_y_start + 40
        visible_h = h - STATUS_H - list_y_start
        _scrollbar(self.screen, rx0 + self.panel_r_w - 6, list_y_start, 4, visible_h,
                   self.prop_scroll, total_h, visible_h)
        return

    # ── Effect Props ──────────────────────────────────────────────────────────

    def _r_effect_props(self, rx0, h, idx, y):
        """Proprietà dell'effetto selezionato nel pannello destro."""
        list_y_start = TOP_BAR_H + 36
        fx = self.scene_data["effects"][idx]
        fx_cat = next((c for c in getattr(self, "effects_catalog", [])
                       if c["id"] == fx.get("effect_id", "")), None)
        
        # ── Proprietà Effetto ─────────────────────────────────────────────────
        mx, my_raw = pygame.mouse.get_pos()

        # Header Effetto
        hdr = _txt(self._TR("prop_fx_hdr"), "sm", FX_C)
        self.screen.blit(hdr, (rx0+12, y)); y += 22
        lbl = fx_cat.get("label", fx.get("effect_id", "?")) if fx_cat else fx.get("effect_id", "?")
        _draw_text(self.screen, lbl.upper(), "md", TXT_HI, rx0+12, y, self.panel_r_w-24); y += 28
        pygame.draw.line(self.screen, BORDER, (rx0+8, y), (rx0+self.panel_r_w-8, y)); y += 16

        # Posizione (Coordinate)
        for lbl_s, val in [("Posizione X:", round(fx.get("x", 0))), ("Posizione Y:", round(fx.get("y", 0)))]:
            _draw_text(self.screen, lbl_s, "sm", TXT_DIM, rx0+12, y)
            sv = _txt(str(val), "mono", TXT_HI)
            self.screen.blit(sv, (rx0 + self.panel_r_w - sv.get_width() - 16, y))
            y += 24
        y += 12
        pygame.draw.line(self.screen, BORDER, (rx0+12, y), (rx0+self.panel_r_w-12, y))
        y += 16

        # Helper per riga proprietà con Slider + Input Box
        def _prop_row(label, key, min_val, max_val, fmt="{:.2f}"):
            nonlocal y
            val = fx.get(key, 0)
            
            _draw_text(self.screen, label, "sm", TXT_DIM, rx0+12, y)
            y += 26
            
            box_w = 60
            box_r = pygame.Rect(rx0+12, y, box_w, 22)
            is_focused = (getattr(self, "_editing_prop", None) == ('effect', idx, key))
            display_val = self._prop_buf if is_focused else fmt.format(val)
            _input_box(self.screen, box_r, display_val, is_focused)
            self._set_hbox_fx(f"box_{key}", 12, y, box_w, 22)
            
            slider_x = rx0 + 12 + box_w + 10
            slider_w = self.panel_r_w - (box_w + 24 + 12)
            slider_rect = (slider_x, y+1, slider_w, 20)
            pwr = 2.0 if key in ("pulse_period", "pulse_min") else 1.0
            _slider(self.screen, slider_rect, val, min_val, max_val, power=pwr, color=FX_C)
            self._set_hbox_fx(f"slider_{key}", 12 + box_w + 10, y+1, slider_w, 20)
            y += 42

        if fx.get("type") == "bubble_tip":
            # ── Specifiche Bubble Tip ─────────────────────────────────────────
            _draw_text(self.screen, self._TR("prop_bubble_preset"), "sm", TXT_DIM, rx0+12, y)
            y += 24
            if getattr(self, "_editing_preset_name", False):
                box_r_name = pygame.Rect(rx0+12, y, self.panel_r_w-24, 26)
                _input_box(self.screen, box_r_name, self._preset_name_buf, True)
                self._set_hbox_fx("preset_name_box", 12, y, self.panel_r_w-24, 26)
                y += 30
            else:
                curr_p = getattr(self, "_preset_selected", "") or "Scegli Preset..."
                drop_r = pygame.Rect(rx0+12, y, 120, 26)
                is_drop_open = getattr(self, "_preset_dropdown_open", False)
                _rect(self.screen, BTN_AC if is_drop_open else BTN, drop_r, radius=4)
                _rect(self.screen, ACCENT if is_drop_open else BORDER, drop_r, 1, radius=4)
                _draw_text(self.screen, curr_p, "sm", TXT_HI, drop_r.x+8, drop_r.y+5, 95)
                # Freccetta dropdown
                pygame.draw.polygon(self.screen, TXT_DIM, [(drop_r.right-14, y+10), (drop_r.right-6, y+10), (drop_r.right-10, y+16)])
                self._set_hbox_fx("preset_drop", 12, y, 120, 26)
                
                # Load/Save
                btn_app_r = pygame.Rect(rx0+140, y, 48, 26)
                _button(self.screen, btn_app_r, "LOAD", _in_rect((mx, my_raw), btn_app_r))
                self._set_hbox_fx("preset_load", 140, y, 48, 26)
                
                btn_sc_r = pygame.Rect(rx0+194, y, 48, 26)
                _button(self.screen, btn_sc_r, "SAVE", _in_rect((mx, my_raw), btn_sc_r))
                self._set_hbox_fx("preset_save", 194, y, 48, 26)
                
                if is_drop_open:
                    # Rendering dropdown lista presets
                    py_start = drop_r.bottom + 2
                    keys = list(self.bubble_presets.keys())
                    for p_key in keys:
                        pr_r = pygame.Rect(drop_r.x, py_start, drop_r.w, 24)
                        phov = _in_rect((mx, my_raw), pr_r)
                        _rect(self.screen, BTN_AC if phov else BTN, pr_r, radius=3)
                        _draw_text(self.screen, p_key, "sm", TXT_HI if phov else TXT, pr_r.x+8, pr_r.y+4, drop_r.w-16)
                        # Hitbox speciale per l'elemento della lista
                        self._set_hbox_fx(f"pitem_{p_key}", 12, py_start, 120, 24)
                        py_start += 25
                    y = py_start
                else:
                    y += 36

            pygame.draw.line(self.screen, BORDER, (rx0+12, y), (rx0+self.panel_r_w-12, y))
            y += 16

            # Testo / Traduzione
            tk = fx.get("text_key", "NEW_TIP")
            _draw_text(self.screen, self._TR("prop_bubble_text_key"), "sm", TXT_DIM, rx0+12, y)
            y += 24
            is_f_tk = (getattr(self, "_editing_prop", None) == ('effect', idx, 'text_key'))
            box_r_tk = pygame.Rect(rx0+12, y, self.panel_r_w-24, 26)
            _input_box(self.screen, box_r_tk, self._prop_buf if is_f_tk else tk, is_f_tk)
            self._set_hbox_fx("tkey_box", 12, y, self.panel_r_w-24, 26)
            y += 34
            
            btn_lng = pygame.Rect(rx0+12, y, self.panel_r_w-24, 28)
            hov_lng = _in_rect((mx, my_raw), btn_lng)
            _button(self.screen, btn_lng, self._TR("prop_btn_manage_trans"), hov_lng)
            self._set_hbox_fx("translations_btn", 12, y, self.panel_r_w-24, 28)
            y += 44
            
            # Trigger
            _draw_text(self.screen, self._TR("prop_bubble_trigger"), "sm", TXT_DIM, rx0+12, y)
            y += 24
            trig = fx.get("trigger", "start_scene")
            labels = {"start_scene": self._TR("prop_bubble_start"), "end_scene": self._TR("prop_bubble_end")}
            for option_id, label in labels.items():
                opt_r = pygame.Rect(rx0+12, y, self.panel_r_w-24, 26)
                is_active = (trig == option_id)
                hov_o = _in_rect((mx, my_raw), opt_r)
                _rect(self.screen, BTN_AC if is_active else (BTN_HO if hov_o else BTN), opt_r, radius=5)
                _rect(self.screen, ACCENT if is_active else BORDER, opt_r, 1 if not hov_o else 2, radius=5)
                _draw_text(self.screen, label, "sm", TXT_HI if is_active else TXT, opt_r.x+10, opt_r.y+5)
                self._set_hbox_fx(f"trigger_{option_id}", 12, y, self.panel_r_w-24, 26)
                y += 30
            y += 12

            # Proprietà Dimensioni e Alpha
            _prop_row(self._TR("prop_bubble_width"), "width", 40, 800, "{:.0f}")
            _prop_row(self._TR("prop_bubble_height"), "height", 30, 600, "{:.0f}")
            _prop_row(self._TR("prop_alpha"), "alpha", 0, 255, "{:.0f}")
            
            # Color Picker Corpo
            y += 4
            _draw_text(self.screen, self._TR("prop_bubble_body_col"), "sm", TXT_DIM, rx0+12, y)
            col = fx.get("color", (252, 252, 255))
            pick_r = pygame.Rect(rx0 + self.panel_r_w - 76, y-1, 60, 20)
            pygame.draw.rect(self.screen, col, pick_r, border_radius=4)
            pygame.draw.rect(self.screen, BORDER, pick_r, 1, border_radius=4)
            self._set_hbox_fx("color_body", self.panel_r_w - 76, y-1, 60, 20)
            y += 32

            # Proprietà Testo
            pygame.draw.line(self.screen, BORDER, (rx0+12, y), (rx0+self.panel_r_w-12, y))
            y += 16
            _draw_text(self.screen, self._TR("prop_text_props_hdr"), "sm", ACCENT, rx0+12, y); y += 26
            _prop_row(self._TR("prop_font_size"), "font_size", 10, 80, "{:.0f}")
            
            # Color Picker Font
            _draw_text(self.screen, self._TR("prop_font_color"), "sm", TXT_DIM, rx0+12, y)
            f_col = fx.get("font_color", (40, 40, 40))
            pick_f_r = pygame.Rect(rx0 + self.panel_r_w - 76, y-1, 60, 20)
            pygame.draw.rect(self.screen, f_col, pick_f_r, border_radius=4)
            pygame.draw.rect(self.screen, BORDER, pick_f_r, 1, border_radius=4)
            self._set_hbox_fx("color_font", self.panel_r_w - 76, y-1, 60, 20)
            y += 40
        
        else:
            # ── Effetti Standard (Glint, Smoke, Flies) ────────────────────────
            ftype = fx.get("type", "")
            
            # --- 1. RAGGIO / AMPIEZZA ---
            lbl_r = self._TR("prop_radius")
            r_min, r_max = 5, 2000
            if ftype == "smoke":    lbl_r, r_min, r_max = self._TR("prop_smoke_width"), 0.2, 100.0
            elif ftype == "glint":  lbl_r = self._TR("prop_glint_radius")
            elif ftype == "flies":  lbl_r = self._TR("prop_flies_area")
            _prop_row(lbl_r, "radius", r_min, r_max, "{:.1f}" if ftype == "smoke" else "{:.0f}")
            
            # --- 2. INTENSITÀ ---
            lbl_i = self._TR("prop_fx_intensity")
            if ftype == "smoke":    lbl_i = self._TR("prop_smoke_opacity")
            elif ftype == "flies":  lbl_i = self._TR("prop_flies_density")
            _prop_row(lbl_i, "intensity", 0.01, 2.0)
            
            # --- 3. VELOCITÀ / PERIODO ---
            lbl_p = self._TR("prop_pulse_period")
            if ftype == "smoke":    lbl_p = self._TR("prop_smoke_speed")
            elif ftype == "flies":  lbl_p = self._TR("prop_flies_speed")
            p_max = 3.5 if ftype == "smoke" else 10.0
            _prop_row(lbl_p, "pulse_period", 0.05, p_max)
            
            # --- 4. MINIMO / DIMENSIONE ---
            lbl_m = self._TR("prop_glint_min")
            if ftype == "smoke":    lbl_m = self._TR("prop_smoke_size")
            elif ftype == "flies":  lbl_m = self._TR("prop_flies_scale")
            m_max = 10.0 if ftype == "smoke" else 2.0
            _prop_row(lbl_m, "pulse_min", 0.0, m_max)
            
            _prop_row(self._TR("prop_phase"), "phase", 0.0, 1.0)
            
            # Color Picker
            y += 8
            _draw_text(self.screen, self._TR("prop_fx_color"), "sm", TXT_DIM, rx0+12, y)
            col = fx.get("color", (255, 215, 60))
            pick_fx_r = pygame.Rect(rx0 + self.panel_r_w - 76, y-1, 60, 20)
            pygame.draw.rect(self.screen, col, pick_fx_r, border_radius=4)
            pygame.draw.rect(self.screen, BORDER, pick_fx_r, 1, border_radius=4)
            self._set_hbox_fx("color_effect", self.panel_r_w - 76, y-1, 60, 20)
            y += 40
            
        y += 10

        # Azioni Finali (Duplica / Elimina)
        pygame.draw.line(self.screen, BORDER, (rx0+12, y), (rx0+self.panel_r_w-12, y))
        y += 16
        half = (self.panel_r_w - 30) // 2
        dup_r = pygame.Rect(rx0 + 12, y, half, 30)
        del_r = pygame.Rect(rx0 + 12 + half + 6, y, half, 30)
        
        hov_dup = _in_rect((mx, my_raw), dup_r)
        hov_del = _in_rect((mx, my_raw), del_r)
        
        _button(self.screen, dup_r, self._TR("prop_btn_duplicate"), hov_dup)
        _button(self.screen, del_r, self._TR("prop_btn_delete"), hov_del, danger=True)
        
        self._set_hbox_fx("dup_btn", 12, y, half, 30)
        self._set_hbox_fx("del_btn", 12 + half + 6, y, half, 30)
        y += 44
        
        # Fine clipping e disegno scrollbar props
        self.screen.set_clip(None)
        total_h = y + self.prop_scroll - list_y_start + 40
        visible_h = h - STATUS_H - list_y_start
        _scrollbar(self.screen, rx0 + self.panel_r_w - 6, list_y_start, 4, visible_h,
                   self.prop_scroll, total_h, visible_h)
