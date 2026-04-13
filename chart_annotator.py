"""
WizTheory Chart Annotator
Draws fib levels, flip zones, and labels on DexScreener screenshots
to match the flashcard style.
"""

from PIL import Image, ImageDraw, ImageFont
import io
import logging

logger = logging.getLogger(__name__)

# Colors (RGB)
COLORS = {
    'purple': (180, 80, 220),      # Flip zone box
    'cyan': (0, 255, 255),         # Labels, arrows, entry
    'red': (255, 80, 80),          # Current price, some fib lines
    'green': (80, 255, 80),        # 382 line
    'yellow': (255, 255, 80),      # 50 line
    'blue': (80, 150, 255),        # 618 line
    'teal': (0, 200, 200),         # 786 line
    'white': (255, 255, 255),      # Text
    'black': (0, 0, 0),            # Text outline
}

# Fib colors
FIB_COLORS = {
    '382': (255, 150, 80),   # Orange
    '50': (200, 200, 80),    # Yellow-ish
    '618': (80, 150, 255),   # Blue
    '786': (80, 220, 220),   # Teal
}


def annotate_chart(
    chart_bytes: bytes,
    engine_result: dict,
    current_price: float = None
) -> bytes:
    """
    Annotate a chart screenshot with WizTheory elements.
    
    Args:
        chart_bytes: Raw PNG screenshot bytes
        engine_result: Dict with fib_levels, flip_zones, swing_high, swing_low, etc.
        current_price: Current token price
    
    Returns:
        Annotated PNG as bytes
    """
    try:
        # Load image
        img = Image.open(io.BytesIO(chart_bytes))
        draw = ImageDraw.Draw(img, 'RGBA')
        
        width, height = img.size
        
        # Get data from engine result
        fib_levels = engine_result.get('fib_levels', {})
        swing_high = engine_result.get('swing_high', 0)
        swing_low = engine_result.get('swing_low', 0)
        impulse_pct = engine_result.get('impulse_pct', 0)
        engine_name = engine_result.get('engine_name', '')
        entry_price = engine_result.get('entry_price', 0)
        
        if not swing_high or not swing_low or swing_high <= swing_low:
            logger.warning("Invalid price range for annotation")
            return chart_bytes
        
        # Chart area estimation (DexScreener layout)
        # Left margin ~60px, right margin ~80px, top ~50px, bottom ~50px
        chart_left = 60
        chart_right = width - 80
        chart_top = 50
        chart_bottom = height - 50
        chart_height = chart_bottom - chart_top
        
        # Price range with padding
        price_range = swing_high - swing_low
        price_high = swing_high + (price_range * 0.1)  # 10% padding above
        price_low = swing_low - (price_range * 0.05)   # 5% padding below
        full_range = price_high - price_low
        
        def price_to_y(price):
            """Convert price to Y coordinate"""
            if full_range <= 0:
                return chart_top + chart_height // 2
            pct_from_top = (price_high - price) / full_range
            return int(chart_top + (pct_from_top * chart_height))
        
        # Try to load font, fallback to default
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # ═══════════════════════════════════════════════════════════════
        # 1. DRAW EXPANSION PERCENTAGE AT TOP
        # ═══════════════════════════════════════════════════════════════
        expansion_text = f"+{impulse_pct:.0f}%"
        exp_y = price_to_y(swing_high) - 30
        exp_x = width // 2
        
        # Draw with outline
        draw_text_with_outline(draw, (exp_x, max(20, exp_y)), expansion_text, 
                               font_large, COLORS['cyan'], COLORS['black'])
        
        # ═══════════════════════════════════════════════════════════════
        # 2. DRAW FIB LEVELS
        # ═══════════════════════════════════════════════════════════════
        for fib_name, fib_price in fib_levels.items():
            if fib_name in ['0', '100', '236', '886']:
                continue  # Skip these
            
            if fib_price <= 0:
                continue
                
            y = price_to_y(fib_price)
            
            # Skip if outside visible area
            if y < chart_top or y > chart_bottom:
                continue
            
            color = FIB_COLORS.get(fib_name, COLORS['white'])
            
            # Draw horizontal line
            draw.line([(chart_left, y), (chart_right, y)], fill=color, width=2)
            
            # Draw label on right side
            label = f"0.{fib_name}" if fib_name != '50' else "0.5"
            draw_text_with_outline(draw, (chart_right + 5, y - 10), label,
                                   font_small, color, COLORS['black'])
        
        # ═══════════════════════════════════════════════════════════════
        # 3. DRAW FLIP ZONE (Purple Box)
        # ═══════════════════════════════════════════════════════════════
        # Flip zone is around the triggered fib level
        triggered_fib = engine_name.replace('+', '').replace(' ', '').replace('fz', '').replace('FZ', '')
        
        if triggered_fib in fib_levels:
            fib_price = fib_levels[triggered_fib]
            
            # Flip zone is typically ±3% around the fib
            zone_top = fib_price * 1.02
            zone_bottom = fib_price * 0.98
            
            y_top = price_to_y(zone_top)
            y_bottom = price_to_y(zone_bottom)
            
            # Draw semi-transparent purple box
            purple_alpha = (180, 80, 220, 80)  # With alpha
            draw.rectangle(
                [(chart_left, y_top), (chart_right, y_bottom)],
                fill=purple_alpha,
                outline=COLORS['purple'],
                width=2
            )
            
            # Draw "FLIP ZONE" label
            zone_center_y = (y_top + y_bottom) // 2
            draw_text_with_outline(draw, (width // 2, zone_center_y), "FLIP ZONE",
                                   font_medium, COLORS['purple'], COLORS['black'])
        
        # ═══════════════════════════════════════════════════════════════
        # 4. DRAW BREAKOUT LABEL
        # ═══════════════════════════════════════════════════════════════
        breakout_y = price_to_y(swing_low * 1.1)  # Just above the low
        breakout_x = chart_left + (chart_right - chart_left) // 3
        
        draw_text_with_outline(draw, (breakout_x, breakout_y), "BREAKOUT",
                               font_medium, COLORS['cyan'], COLORS['black'])
        
        # Draw arrow pointing down-right
        arrow_start = (breakout_x + 80, breakout_y + 10)
        arrow_end = (breakout_x + 120, breakout_y + 40)
        draw.line([arrow_start, arrow_end], fill=COLORS['cyan'], width=3)
        
        # ═══════════════════════════════════════════════════════════════
        # 5. DRAW ENTRY LABEL
        # ═══════════════════════════════════════════════════════════════
        if entry_price and entry_price > 0:
            entry_y = price_to_y(entry_price)
            entry_x = chart_right - 150
            
            draw_text_with_outline(draw, (entry_x, entry_y - 25), "ENTRY",
                                   font_medium, COLORS['cyan'], COLORS['black'])
            
            # Draw curved arrow showing bounce
            # Simple version: just draw an upward arrow
            arrow_points = [
                (entry_x + 30, entry_y),
                (entry_x + 50, entry_y - 40),
                (entry_x + 70, entry_y - 60),
            ]
            draw.line(arrow_points, fill=COLORS['cyan'], width=3)
        
        # ═══════════════════════════════════════════════════════════════
        # 6. DRAW CURRENT PRICE (if provided)
        # ═══════════════════════════════════════════════════════════════
        if current_price and current_price > 0:
            cp_y = price_to_y(current_price)
            if chart_top < cp_y < chart_bottom:
                # Red dashed line effect (draw short segments)
                for x in range(chart_left, chart_right, 20):
                    draw.line([(x, cp_y), (x + 10, cp_y)], fill=COLORS['red'], width=2)
                
                # Price label
                price_str = format_price(current_price)
                draw.rectangle([(chart_right - 5, cp_y - 12), (width - 5, cp_y + 12)],
                               fill=COLORS['red'])
                draw.text((chart_right + 2, cp_y - 8), price_str, 
                          fill=COLORS['white'], font=font_small)
        
        # Convert back to bytes
        output = io.BytesIO()
        img.save(output, format='PNG', quality=95)
        output.seek(0)
        
        logger.info(f"✅ Chart annotated successfully")
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"❌ Chart annotation failed: {e}")
        return chart_bytes  # Return original on failure


def draw_text_with_outline(draw, pos, text, font, fill_color, outline_color, outline_width=2):
    """Draw text with outline for better visibility"""
    x, y = pos
    # Draw outline
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color, anchor="mm")
    # Draw main text
    draw.text((x, y), text, font=font, fill=fill_color, anchor="mm")


def format_price(price: float) -> str:
    """Format price for display"""
    if price < 0.0001:
        return f"{price:.10f}"
    elif price < 0.01:
        return f"{price:.8f}"
    elif price < 1:
        return f"{price:.6f}"
    else:
        return f"{price:.4f}"


# Test function
if __name__ == "__main__":
    print("Chart annotator module loaded successfully")
