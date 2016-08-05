#!/usr/bin/env python3

import argparse
import random
import sys
import hashlib
import struct
import math
from worldmap import WorldMap,MapGrid
import ips

VERSION = "1.2-beta-2016.08.05"
#sha1sums of various roms
prg0sums = ['6a50ce57097332393e0e8751924fd56456ef083c', #Dragon Warrior (U) (PRG0) [!].nes
            '66330df6fe3e3c85adb8183721e5f88c149e52eb', #Dragon Warrior (U) (PRG0) [b1].nes
            '49974889619f1d8c39b6c20fa208c62a0a73ecce', #Dragon Warrior (U) (PRG0) [b1][o1].nes
            'd98b8a3fc93bb2f1f5016326556b68998dd5f85d', #Dragon Warrior (U) (PRG0) [b2].nes
            'e81a693efe322be9584c97b55c6d7ae38ae44a66', #Dragon Warrior (U) (PRG0) [o1].nes
            '6e1a52b7b3a13494536bbab7248690861665001a', #Dragon Warrior (U) (PRG0) [o2].nes
            '3077d5bd5c5c3744398b122d5ee1bba7055c8d45'] #Dragon Warrior (U) (PRG0) [o3].nes
prg1sums = ['1ecc63aaac50a9612eaa8b69143858c3e48dd0ae'] #Dragon Warrior (U) (PRG1) [!].nes

class Rom:
  # alphabet - 0x5f is breaking space, 60 is non-breaking (I think)
  alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" + \
             "__'______.,-_?!_)(_______________  "
  # Slices for various data. Offsets include iNES header.
  token_dialogue_slice = slice(0xa238, 0xa299)
  will_not_work_slice = slice(0xad95, 0xadad)
  chest_content_slice = slice(0x5de0, 0x5e59, 4)
  enemy_stats_slice = slice(0x5e5b, 0x60db)
  warps_slice = slice(0xf3d8, 0xf50b)
  zones_slice = slice(0xf55f, 0xf5c3)
  zone_layout_slice = slice(0xf532, 0xf552)
  mp_req_slice = slice(0x1d63, 0x1d6d) #mp requirements for each spell
  xp_req_slice = slice(0xf36b, 0xf3a7)
  player_stats_slice = slice(0x60dd, 0x6191)
  weapon_shop_inv_slice = slice(0x19a1, 0x19cc)
  new_spell_slice = slice(0xeaf9, 0xeb1f, 4)
  chests_slice = slice(0x5ddd, 0x5e59)
  title_text_slice = slice(0x3f36, 0x3fc5)

  token_slice = slice(0xe11e, 0xe12b, 6)
  flute_slice = slice(0xe15d, 0xe16a, 6)
  armor_slice = slice(0xe173, 0xe180, 6)

  encounter_1_slice = slice(0xcd64, 0xcd71, 6) # axe knight
  encounter_2_slice = slice(0xcd7b, 0xcd88, 6) # green dragon
  encounter_3_slice = slice(0xcd98, 0xcda5, 6) # golem
  encounter_1_run_slice = slice(0xe8e7, 0xe8f4, 6) # axe knight
  encounter_2_run_slice = slice(0xe90e, 0xe91b, 6) # green dragon
  encounter_3_run_slice = slice(0xe93b, 0xe948, 6) # golem
  encounter_enemies_slice = slice(0xcd74, 0xcdaf, 29)
  encounter_2_kill_slice = slice(0xe97e, 0xe985, 6) # green dragon
  encounter_3_kill_slice = slice(0xe990, 0xe997, 6) #golem

  def __init__(self, filename):
    input_file = open(filename, 'rb')
    self.rom_data = bytearray(input_file.read())
    input_file.close()
    self.revert()

  def sha1(self, data=None):
    """
    Returns a sha1 checksum of the rom data
    """
    if data:
      return hashlib.sha1(data).hexdigest()
    else:
      return hashlib.sha1(self.rom_data).hexdigest()

  def verify_checksum(self):
    """
    Verifies the checksum of the input ROM against known ROM checksums.
    """
    digest = self.sha1()
    if digest in prg0sums:
      return 0
    elif digest in prg1sums:
      return 1
    return False

  def ascii2dw(self, text):
    """
    Converts an ascii string to bytes suitable for insertion into the ROM.

    :Parameters:
      text : string
        The text to be converted.

    rtype: bytearray
    return: Dialoge bytes suitable for insertion into the ROM.
    """
    return bytearray([self.alphabet.find(i) for i in text])


  def dw2ascii(self, dialogue):
    """
    Converts a string of bytes from the ROM to ascii text.

    :Parameters:
      dialogue : bytearray
        The bytes from the ROM to be converted. 
  
    rtype: string
    return: The ascii text after conversion.
    """
    return ''.join([self.alphabet[i] for i in list(dialogue)])

  def shuffle_chests(self):
    """
    Shuffles the contents of all chests in the game. Checks are used to ensure no
    quest items are located in Charlock chests.
    """
    chest_contents = self.chests[3::4]
    for i in range(len(chest_contents)):
      # replace the harp with a key.
      if chest_contents[i] == 0xd:
        chest_contents[i] = 3
      # change all gold to large gold stash
      if (chest_contents[i] >= 18 and chest_contents[i] <= 20):
        chest_contents[i] = 21
      # 50/50 chance to have erdrick's token in a chest. If not, large gold.
      if chest_contents[i] == 0x17:
        if random.randint(0,1):
          self.token_loc[0] = 0 # remove token from the ground
          chest_contents[i] = 10 # put it in a chest
        else:
          chest_contents[i] = 3 # else put in a key.


    random.shuffle(chest_contents)

    # make sure required quest items aren't in Charlock
    charlock_chests = chest_contents[11:17] + chest_contents[24:25]
    charlock_chest_indices = (11, 12, 13, 14, 15, 16, 24)
    quest_items = (10, 13, 15, 16)
    for item in quest_items:
      if (item in charlock_chests):
        for i in charlock_chest_indices:
          if chest_contents[i] == item:
            # this could probably be cleaner...
            j = self.non_charlock_chest()
            while chest_contents[j] in quest_items:
              j = self.non_charlock_chest()
            chest_contents[j], chest_contents[i] = chest_contents[i], chest_contents[j]

    # make sure there's a key in the throne room
    if not (3 in chest_contents[4:7]):
      for i in range(len(chest_contents)):
        if chest_contents[i] == 3:
          j = random.randint(4, 6)
          # if key is in charlock and chest[j] contains a quest item, try again
          while (i in charlock_chest_indices and (chest_contents[j] in quest_items)):
            j = random.randint(4, 6)
          chest_contents[j], chest_contents[i] = chest_contents[i], chest_contents[j]
          break

    self.chests[3::4] = chest_contents

  def non_charlock_chest(self):
    """
    Gives a random index of a chest that is not in Charlock

    rtype: int
    return: A chest index that is not in Charlock.
    """
    chest = random.randint(0, 23)
    # avoid 11-16 and chest 24 (they are in charlock)
    chest = chest + 6 if (chest > 10) else chest
    chest = chest + 1 if (chest > 23) else chest
    return chest

  def randomize_attack_patterns(self, ultra=False):
    """
    Randomizes attack patterns of enemies (whether or not they use spells/fire 
    breath).

    :Parameters:
      ultra : bool
        Whether or not to apply ultra randomization
    """
    new_patterns = [] # attack patterns
    new_ss_resist = self.enemy_stats[4::16] 
    for i in range(38):
      new_ss_resist[i] |= 0xf
      if random.randint(0,1): # 50/50 chance
        resist = random.randint(0,round(i/5))
        new_ss_resist[i] &= (0xf0 | resist)
        if ultra:
            new_patterns.append((random.randint(0,255)))
        else:
          if i <= 20:
            # heal, sleep, stopspell, hurt
            new_patterns.append((random.randint(0,11) << 4) | random.randint(0,3))
          elif i < 30:
            # healmore, heal, sleep, stopspell, fire breath, hurtmore
            new_patterns.append((random.randint(0,15) << 4) | random.randint(4, 11))
          else:
            # healmore, sleep, stopspell, strong fire breath, fire breath, hurtmore
            #we'll be nice and not give Axe Knight Dragonlord's breath.
            slot2 = random.randint(4, 11) if i == 33 else random.randint(4, 15)
            new_patterns.append((random.choice((0, 1, 3)) << 6) | 
                (random.randint(0, 3) << 4) | slot2)
      else:
        new_patterns.append(0)
    new_patterns.append(87) #Dragonlord form 1
    new_patterns.append(14) #Dragonlord form 2
    self.enemy_stats[3::16] = bytearray(new_patterns)
    self.enemy_stats[4::16] = bytearray(new_ss_resist)

  def shuffle_towns(self):
    """
    Shuffles the locations of towns on the map.
    """
    self.owmap.shuffle_warps()

  def generate_map(self):
    """
    Generates a new overworld map.
    """
    if not self.owmap.generate():
      self.owmap.revert()
      return False
    # Stick encounter 3 in Charlock for now...
    self.encounter_3_loc = (6, 25, 22)
    self.encounter_3_kill[1] = self.encounter_3_loc[0]
    # Let's not remember killing it...
    self.encounter_3_kill[1] = 0
    return True

  def randomize_zone_layout(self):
    """
    Randomizes enemy zone layout on the overworld map.
    """
    for i in range(len(self.zone_layout)):
      self.zone_layout[i] = random.randint(1,15) << 4 | \
                            random.randint(1,15)
    # set tantegel's zone to 0
    tx,ty = self.owmap.warps_from[self.owmap.tantegel_warp][1:]
    tantegel_zone_index = (ty // 15 * 8) + tx // 15
    if tantegel_zone_index % 2:
      self.zone_layout[tantegel_zone_index // 2] &= 240 # second nybble
    else:
      self.zone_layout[tantegel_zone_index // 2] &= 15 # first nybble

  def randomize_zones(self, ultra=False):
    """
    Randomizes which enemies are present in each zone.

    :Parameters:
      ultra : bool
        Whether or not to apply ultra randomization
    """
    new_zones = list()
    if ultra:
      # randomize zone locations
      if self.owmap.generated:
        self.randomize_zone_layout()
      # zone 0-1
      for i in range(0,5):
        new_zones.append(random.randint(0, 6))
      for i in range(0,5):
        if self.owmap.generated:
          new_zones.append(random.randint(0, 37))
        else:
          new_zones.append(random.randint(0, 6))
      # zones 2-15
      for i in range(0,70):
        new_zones.append(random.randint(0, 37))
      # zones 16-18 (Charlock)
      for i in range(0,15):
        new_zones.append(random.randint(29,37))
      # zone 19
      for i in range(0,5):
        new_zones.append(random.randint(0, 37))

      # randomize forced encounter enemies:
      # Golem, Axe Knight, Blue Dragon, Stoneman, Armored Knight, Red Dragon
      for i in range(3):
        self.encounter_enemies[i] = random.choice((24, 33, 34, 35, 36, 37))
      self.encounter_2_kill[0] = self.encounter_enemies[1]
      self.encounter_3_kill[0] = self.encounter_enemies[2]
    else:
      #zone 0
      for j in range(5): 
        new_zones.append(int(random.randint(0, 6)/2))

      # zones 1-13 (Overworld)
      for i in range(1, 14):
        for j in range(5):
          enemy = random.randint(i * 2 - 2, min(37,round(i*3)))
          while enemy == 24: # don't add golem
            enemy = random.randint(i * 2 - 2, min(37,round(i*3)))
          new_zones.append(enemy)

      #zone 14 - Garin's Grave?
      for j in range(5): 
        new_zones.append(random.randint(7, 17))

      #zone 15 - Lower Garin's Grave
      for j in range(5): 
        new_zones.append(random.randint(15, 23))

      # zone 16-18 - Charlock
      for i in range(16, 19):
        for j in range(5):
          new_zones.append(random.randint(13+i, 37))

      # zone 19 - Rimuldar Tunnel
      for j in range(5):
        new_zones.append(random.randint(3, 11))
    self.zones = new_zones


  def randomize_shops(self):
    """
    Randomizes the items available in each weapon shop
    """
    weapons = (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 14, 15, 16)
    new_shop_inv = []
    # add 5 items to each shop
    for i in range(7):
      this_shop = []
      while(len(this_shop) < 5):
        new_item = random.choice(weapons)
        if not new_item in this_shop:
          this_shop.append(new_item)
      new_shop_inv.append(this_shop)

    # add an extra item to one shop since we have 36 slots.
    six_item_shop = random.randint(0, 6)
    new_item = random.choice(weapons)
    while new_item in new_shop_inv[six_item_shop]:
      new_item = random.choice(weapons)
    new_shop_inv[six_item_shop].append(new_item)
    
    # create the bytearray to insert into the rom. Shops are separated by an 
    # 0xfd byte
    self.shop_inventory = []
    for shop in new_shop_inv:
      shop.sort()
      self.shop_inventory += shop + [0xfd]


  def shuffle_searchables(self):
    """
    Shuffles the 3 searchable items in the game. (E.Armor, F.Flute, E.Token)
    """
    # move the token, then shuffle
    tantegel = self.owmap.warps_from[self.owmap.tantegel_warp][1:3]
    grid = MapGrid(self.owmap.grid)
    new_token_loc = self.owmap.accessible_land(grid, tuple(tantegel))
    self.token_loc[1:3] = new_token_loc

    searchables = [self.token_loc, self.flute_loc, self.armor_loc]
    random.shuffle(searchables)
    self.token_loc = searchables[0]
    self.flute_loc = searchables[1]
    self.armor_loc = searchables[2]

  def randomize_growth(self, ultra=False):
    """
    Randomizes player growth.
    
    :Parameters:
      ultra : bool
        Whether or not to apply ultra randomization.
    """
    
    player_str = list(self.player_stats[0:180:6])
    player_agi = list(self.player_stats[1:180:6])
    player_hp  = list(self.player_stats[2:180:6])
    player_mp  = list(self.player_stats[3:180:6])

    if ultra:
      # set these to make DL normally beatable at lvl 15
      player_str = inverted_power_curve( 4, 155, 1.18)
      player_agi = inverted_power_curve( 4, 145, 1.32)
      player_hp  = inverted_power_curve(10, 230, 0.98)
      player_mp  = inverted_power_curve( 0, 220, 0.95)
    else:
      for i in range(len(player_str)):
        player_str[i] = round(player_str[i] * random.uniform(0.8, 1.2))
      for i in range(len(player_agi)):
        player_agi[i] = round(player_agi[i] * random.uniform(0.8, 1.2))
      for i in range(len(player_hp)):
        player_hp[i] = round(player_hp[i] * random.uniform(0.8, 1.2))
      for i in range(len(player_mp)):
        player_mp[i] = round(player_mp[i] * random.uniform(0.8, 1.2))

    player_str.sort()
    player_agi.sort()
    player_hp.sort()
    player_mp.sort()

    self.player_stats[0:180:6] = player_str
    self.player_stats[1:180:6] = player_agi
    self.player_stats[2:180:6] = player_hp
    self.player_stats[3:180:6] = player_mp

  def randomize_spell_learning(self, ultra=False):
    """
    Randomizes the level at which spells are learned.

    :Parameters:
      ultra : bool
        Whether or not to use ultra randomization.
    """
    self.move_repel() # in case this hasn't been called yet.
    # choose the levels for new spells
    if ultra:
      for i in range(len(self.new_spell_levels)):
        self.new_spell_levels[i] = random.randint(0, 16)
    else:
      for i in range(len(self.new_spell_levels)):
        self.new_spell_levels[i] += random.randint(-2, 2)
    self.update_spell_masks()

  def update_spell_masks(self):
    """
    Updates the spell masks to be written to the rom, based on the data in 
    player_stats.
    """
    new_masks = []
    player_mp = self.player_stats[3::6]
    #adjust the spell masks to fit the new levels
    for i in range(30):
      mask = 0
      for j in range(len(self.new_spell_levels)):
        if self.new_spell_levels[j] <= i+1:
          mask |= 1 << j
      new_masks.append(mask)
      if mask: # give the player at least 6 mp if they have a spell to use.
        player_mp[i] = max(6, player_mp[i])
    mask1 = []
    mask2 = []
    # split the masks for use in the rom
    for mask in new_masks:
      mask1.append(mask & 0xff)
      mask2.append(mask >> 8)

    self.player_stats[3::6] = player_mp
    self.player_stats[5::6] = mask1
    self.player_stats[4::6] = mask2

  def update_drops(self):
    """
    Raises enemy XP and gold drops to those of the remakes.
    """
    remake_xp = [  1,  2,  3,  4,  8, 12, 16, 14, 15, 18, 20, 25, 28, 
                  31, 40, 42,255, 47, 52, 58, 58, 64, 70, 72,255,  6, 
                  78, 83, 90, 95,135,105,120,130,180,155,172,255,  0,  0]
    # These are +1 for proper values in the ROM
    remake_gold=[  2,  4,  6,  8, 16, 20, 25, 21, 19, 30, 25, 42, 50, 
                  48, 60, 62,  6, 75, 80, 95,110,105,110,120, 10,255,
                 150,135,148,155,160,169,185,165,150,148,152,143,  0,  0]
    self.enemy_stats[6::16] = bytearray(remake_xp)
    self.enemy_stats[7::16] = bytearray(remake_gold)

  def update_mp_reqs(self, ultra=False):
    """
    Lowers the MP requirements of spells to that of the remake
    """
    #magic required for each spell, in order
    self.mp_reqs = [3, 2, 2, 2, 2, 6, 8, 2, 8, 5]
#    if ultra:
#      for i in range(10):
#        self.mp_reqs[i] = random.randint(1, 8)

  def lower_xp_reqs(self, ultra=False):
    """
    Lowers the XP requirements for a faster game.
    """
    xp = struct.unpack( "<HHHHHHHHHHHHHHHHHHHHHHHHHHHHHH", self.xp_reqs )
    if ultra:
      xp = [round(x * 0.5) for x in xp]
    else:
      xp = [round(x * 0.75) for x in xp]
    self.xp_reqs = struct.pack( "<HHHHHHHHHHHHHHHHHHHHHHHHHHHHHH", *xp )

  def update_enemy_hp(self):
    """
    Updates HP of enemies to that of the remake, where possible.
    """
    #dragonlord hp should be 204 and 350, but we want him beatable at lv 18
    remake_hp = [  2,  3,  5,  7, 12, 13, 13, 22, 26, 35, 16, 24, 28, 
                  18, 33, 39,  3, 48, 37, 35, 44, 37, 40, 40,153,110, 
                  47, 48, 38, 70, 72, 74, 65, 67, 98,135, 99,106,100,165]
    # randomize Dragonlord's second form HP somewhat 
    remake_hp[-1] -= random.randint(0, 15) # 150 - 165
    self.enemy_stats[2::16] = bytearray(remake_hp)

  def move_repel(self):
    """
    Moves the repel spell to level 8
    """
    self.new_spell_levels[7] = 8
    self.update_spell_masks()

  def revert(self):
    """
    Reverts all previous changes to the ROM
    """
    self.patch = ips.Patch()
    self.owmap = WorldMap(self.rom_data)
    self.enemy_stats = self.rom_data[self.enemy_stats_slice]
    self.mp_reqs = self.rom_data[self.mp_req_slice]
    self.xp_reqs = self.rom_data[self.xp_req_slice]
    self.zones = self.rom_data[self.zones_slice]
    self.zone_layout = self.rom_data[self.zone_layout_slice]
    self.shop_inventory = self.rom_data[self.weapon_shop_inv_slice]
    self.token_loc = self.rom_data[self.token_slice]
    self.flute_loc = self.rom_data[self.flute_slice]
    self.armor_loc = self.rom_data[self.armor_slice]
    self.encounter_1_loc = self.rom_data[self.encounter_1_slice] # axe knight
    self.encounter_2_loc = self.rom_data[self.encounter_2_slice] # green dragon
    self.encounter_3_loc = self.rom_data[self.encounter_3_slice] # golem
    self.encounter_enemies = self.rom_data[self.encounter_enemies_slice]
    # set position 1 to these to disable remembering of killing them.
    self.encounter_2_kill = self.rom_data[self.encounter_2_kill_slice]
    self.encounter_3_kill = self.rom_data[self.encounter_3_kill_slice]
    self.player_stats = self.rom_data[self.player_stats_slice]
    self.new_spell_levels = self.rom_data[self.new_spell_slice]
    self.chests = self.rom_data[self.chests_slice]
    self.title_screen_text = self.rom_data[self.title_text_slice]
    # patch format - address: (*data)
      # fighter's ring fix
    self.add_patches({
      # fighter's ring fix
      0xf10c: (0x20, 0x54, 0xff, 0xea),
      0xff64: (0x85, 0xcd, 0xa5, 0xcf, 0x29, 0x20, 0xf0, 0x07, 0xa5, 
                  0xcc, 0x18, 0x69, 0x02, 0x85, 0xcc, 0xa5, 0xcf, 0x60),
      0x43a: (0x47,), # add new stairs to the throne room
      0x2b9: (0x45,), # add new stairs to the 1st floor
      0x2d7: (0x66,), # add a new exit to the first floor
      # replace the usless grave warps with some for tantegel
      0xf45f: (5, 1, 8),
      0xf4f8: (4, 1, 7),
      0x1298: (0x22,), #remove the top set of stairs for the old warp in the grave
      0xdbce: (15,), # buff the heal spell
      # Removes the 2 blocks around the northern shrine guardian so you can 
      # walk around him.
      0xd77: (0x66,), 0xd81: (0x66,),
      # Sets the encounter rate of Zone 0 to be the same as other zones.
      0xea51: (0xad, 0x07, 0x01, 0xea, 0xea),
    })
      # Sets the encounter rate of Zone 0 to be the same as other zones.
    self.add_patch(0xced1, 0xea, 13)


  def speed_hacks(self):
    """
    Adds some hacks to speed up the game play
    """
    self.add_patches({
      # Following are some speed hacks from @gameboy9
      # speed up the text
      0x7a43: (0xea, 0xea, 0xea),
      # speed up encounter intros
      0xe41a: (0xea, 0xea, 0xea),
      0xe44d: (0xea, 0xea, 0xea),
      0xc53f: (0xea, 0xea, 0xea),
      0xef49: (2,), # speed up the player attack animation
      0xed45: (3,), # speed up the enemy attack animation
      # speed up the death music
      0x4d38: (0x1,), 0x4d3c: (0x6,), 0x4d4b: (0x7,), 0x4d4d: (0x8,), 0x4d4f: (0x8,),
      0x4d51: (0x8,), 0x4d53: (0x2,), 0x4d55: (0x2,), 0x4d57: (0x10,),
      # speed up the level up music
      0x463b: (0xff,),
      # speed up the battle win music
      0x4724: (1,), 0x472a: (1,), 0x472c: (1,), 0x472e: (1,),
    })

  def token_dialogue(self):
    """
    Generates new dialogue data for the NPC who tells you where the token is.
)
    rtype: bytearray
    return: new data to replace the npc dialogue.
    """
    if self.token_loc[0] == 1:
      x, y = self.token_loc[1:3]
    elif self.flute_loc[0] == 1:
      x, y = self.flute_loc[1:3]
    elif self.armor_loc[0] == 1:
      x, y = self.armor_loc[1:3]
    else:
      return (self.ascii2dw("Thou must go and fight!") + 
        bytearray([0xfc, 0xfb, 0x50]) + 
        self.ascii2dw( "Go forth, descendent of Erdrick, "
         "I have complete faith in thy victory! "))
    tx, ty = self.owmap.warps_from[self.owmap.tantegel_warp][1:3]
    north_south = "north" if y < ty else "south"
    east_west = "west" if x < tx else "east"
    return (self.ascii2dw("Thou may go and search.") + 
      bytearray([0xfc, 0xfb, 0x50]) + self.ascii2dw(
      ("From Tantegel Castle travel %2d leagues to the %s and %2d to the %s.") % 
       (abs(y - ty), north_south, abs(x - tx), east_west)))

  def commit(self):
    """
    Commits all changes to the ROM
    """
    orig_data = self.rom_data[:]
    self.add_patch(self.will_not_work_slice, self.ascii2dw("The spell had no effect."))
    self.add_patch(self.token_dialogue_slice, self.token_dialogue())
    self.add_patch(self.enemy_stats_slice, self.enemy_stats )
    self.add_patch(self.mp_req_slice, self.mp_reqs)
    self.add_patch(self.xp_req_slice, self.xp_reqs)
    self.add_patch(self.zones_slice, self.zones)
    self.add_patch(self.zone_layout_slice, self.zone_layout)
    self.add_patch(self.weapon_shop_inv_slice, self.shop_inventory)
    self.add_patch(self.token_slice, self.token_loc)
    self.add_patch(self.flute_slice, self.flute_loc)
    self.add_patch(self.armor_slice, self.armor_loc)
    self.add_patch(self.encounter_1_slice, self.encounter_1_loc )
    self.add_patch(self.encounter_2_slice, self.encounter_2_loc )
    self.add_patch(self.encounter_3_slice, self.encounter_3_loc )
    self.add_patch(self.encounter_1_run_slice, self.encounter_1_loc )
    self.add_patch(self.encounter_2_run_slice, self.encounter_2_loc )
    self.add_patch(self.encounter_3_run_slice, self.encounter_3_loc )
    self.add_patch(self.encounter_enemies_slice, self.encounter_enemies)
    # update the kill bit code)
    self.add_patch(self.encounter_2_kill_slice, self.encounter_2_kill)
    self.add_patch(self.encounter_3_kill_slice, self.encounter_3_kill)

    self.add_patch(self.player_stats_slice, self.player_stats)
    self.add_patch(self.new_spell_slice, self.new_spell_levels)
    self.add_patch(self.chests_slice, self.chests)
    self.add_patch(self.title_text_slice, self.title_screen_text)

    self.patch.combine(self.owmap.patch)
    self.patch.apply(self.rom_data)

  def add_patch(self, addr, values, size=None):
    """
    Adds a new manual rom patch
    :Parameters:
      addr : int
        The address where the new data is to be applied
      values : array
        The first argument should be the distance between each byte to be placed
        in the rom. The rest is the data to be patched into the ROM
      size : int
        The size of the patch if this is an rle patch (the same byte repeated
        over and over), otherwise None.
    """
    if not isinstance(addr, slice):
      self.patch.add_record(addr, values, size)
    elif addr.step in (1, None):
      self.patch.add_record(addr.start, values, size)
    else:
      for i in range(len(values)):
        self.patch.add_record(addr.start + i * addr.step, values[i])

  def add_patches(self, patchdict):
    """
    Adds new manual patches
    :Parameters:
      patchdict : dict
        A dictionary containing patches in the form addr: value. RLE records 
        cannot be added via this method.
    """
    self.patch.add_records(patchdict)

  def write(self, output_filename, content=None):
    """
    Writes out the new ROM file
    :Parameters:
      output_filename : string
        The name of the new file
    """
    outputfile = open(output_filename, 'wb')
    if content:
      outputfile.write(content)
    else:
      outputfile.write(self.rom_data)
    outputfile.close()

  def update_title_screen(self, seed, flags):
    """
    Adds flags and seed number to the title screen

    :Parameters:
      seed : int
        The random seed used to generate this ROM.
      flags: str
        The flags used to generate this ROM.
    """
    # There are no lower case characters in the title screen alphabet :(
    # I'm not sure how to deal with this yet wrt flags.
    padding = lambda s: struct.pack('BBB', 0xf7, s, 0x5f)
    padline = lambda p: padding(math.floor((32 - len(p))/2)) + self.ascii2dw(p) + \
                    padding(math.ceil((32 - len(p))/2)) + b'\xfc'
    blank_line = struct.pack('BBBB', 0xf7, 32, 0x5f, 0xfc)
    new_text = b''
    new_text += blank_line
    new_text += padline("RANDOMIZER")
    new_text += blank_line
    new_text += padline(VERSION.upper())
    new_text += blank_line
    new_text += blank_line
    new_text += blank_line
    new_text += blank_line
    new_text += padline("FLAGS " + flags.upper())
    new_text += blank_line
    new_text += padline("SEED " + str(seed))
    new_text += blank_line

    needed_bytes = len(self.title_screen_text) - len(new_text) - 4
    if needed_bytes > 31: # current data is too short...
      new_text = new_text[:-len(blank_line)] + (b'\x5f' * 32 + b'\xfc')
      needed_bytes = len(self.title_screen_text) - len(new_text) - 4

    new_text += b'\x5f' * needed_bytes + padding(32 - needed_bytes) + b'\xfc'
    new_text = new_text.replace(b'\x47', b'\x61').replace(b'\x49', b'\x63')

    self.title_screen_text = new_text
    

def inverted_power_curve(min_, max_, power, count=30):
  range_ = max_ - min_
  p_range = range_ ** (1/power)
  points = []
  for i in range(count):
    points.append(round(max_ - ((random.random() * p_range) ** power)))
  points.sort()
  return points

def main():
  
  parser = argparse.ArgumentParser(prog="DWRandomizer",
      description="A randomizer for Dragon Warrior for NES")
  parser.add_argument("-r","--no-remake", action="store_false",
      help="Do not set enemy HP, XP/Gold drops and MP use up to that of the "
           "remake. This will make grind times much longer.")
  parser.add_argument("-c","-C","--no-chests", action="store_false",
      help="Do not randomize chest contents.")
  parser.add_argument("-d","-D","--defaults", action="store_true",
      help="Run the randomizer with the default options.")
  parser.add_argument("--force", action="store_false", 
      help="Skip checksums and force randomization. This may produce an invalid"
           " ROM if the incorrect file is used.")
  parser.add_argument("-i","-I","--no-searchitems", action="store_false", 
      help="Do not randomize the locations of searchable items (Fairy Flute, "
           "Erdrick's Armor, Erdrick's Token).")
  parser.add_argument("--ips", action="store_true", 
      help="Also create an IPS patch for the original ROM")
  parser.add_argument("-f","--fast-leveling", action="store_true", 
      help="Set XP requirements for each level to 75%% of normal.")
  parser.add_argument("-F","--very-fast-leveling", action="store_true", 
      help="Set XP requirements for each level to 50%% of normal.")
  parser.add_argument("-g","--no-growth", action="store_false", 
      help="Do not randomize player stat growth.")
  parser.add_argument("-G","--ultra-growth", action="store_true", 
      help="Enable ultra randomization of player stat growth.")
  parser.add_argument("-H","--speed-hacks", action="store_true", 
      help="Apply game speed hacks (experimental)")
  parser.add_argument("-m","--no-spells", action="store_false", 
      help="Do not randomize the level spells are learned.")
  parser.add_argument("-M","--ultra-spells", action="store_true", 
      help="Enable ultra randomization of the level spells are learned.")
  parser.add_argument("--no-map", action="store_false", 
      help="Do not generate a new world map.")
  parser.add_argument("-p","--no-patterns", action="store_false", 
      help="Do not randomize enemy attack patterns.")
  parser.add_argument("-P","--ultra-patterns", action="store_true", 
      help="Enable ultra randomization of enemy attack patterns.")
  parser.add_argument("-s","-S","--seed", type=int, 
      help="Specify a seed to be used for randomization.")
  parser.add_argument("-t","-T","--no-towns", action="store_false", 
      help="Do not randomize towns.")
  parser.add_argument("-w","-W","--no-shops", action="store_false", 
      help="Do not randomize weapon shops.")
  parser.add_argument("-u","-U","--ultra", action="store_true", 
      help="Enable all 'ultra' options.")
  parser.add_argument("-z","--no-zones", action="store_false", 
      help="Do not randomize enemy zones.")
  parser.add_argument("-Z","--ultra-zones", action="store_true", 
      help="Enable ultra randomization of enemy zones.")
  parser.add_argument("-v","-V","--version", action="version", 
      version="%%(prog)s %s" % VERSION)
  parser.add_argument("filename", help="The rom file to use for input")
  args = parser.parse_args()

  # if the user didn't enter any flags, ask for options.
  if len(sys.argv) <= 2: 
    prompt_for_options(args)

  randomize(args)

  # So the command prompt doesn't just disappear
  if sys.platform == 'win32':
    print("\n\n")
    input("Press enter to exit...")

def prompt_for_options(args):
  """
  Prompts the user for randomizer options
  """
  print()
  while True:
    seed = input("Enter seed number (leave blank for random seed): ")
    if seed:
      try:
        args.seed = int(seed)
        break
      except:
        print("\nThat is not a valid number. ", end="")
    else:
      break

  custom = True

  mode = input("\nRandomization mode - ultra, normal, custom (u/n/C): ")
  if (mode.lower().startswith("u")):
    args.ultra = True
    custom = False
  elif (mode.lower().startswith("n")):
    custom = False

  mode = input("\nLeveling speed - normal, fast, very fast (N/f/v): ")
  if (mode.lower().startswith("v")):
    args.very_fast_leveling = True
  elif (mode.lower().startswith("f")):
    args.fast_leveling = True

  if custom:
    if input("\nGenerate a random world map? (Y/n) ").lower().startswith("n"):
      args.no_map = False

    if input("\nApply hacks to speed up game play (experimental)? (y/N) ").lower().startswith("y"):
      args.speed_hacks = True

    if args.no_map:
      if input("\nRandomize town & cave locations? (Y/n) ").lower().startswith("n"):
        args.no_towns = False

    if input("\nRandomize weapon shops? (Y/n) ").lower().startswith("n"):
      args.no_shops = False

    if input("\nRandomize chests? (Y/n) ").lower().startswith("n"):
      args.no_chests = False

    if input("\nRandomize searchable items? (Y/n) ").lower().startswith("n"):
      args.no_searchitems = False

    growth = input("\nStat growth randomization - ultra, default, none (u/D/n): ")
    if (growth.lower().startswith("u")):
      args.ultra_growth = True
    elif (growth.lower().startswith("n")):
      args.growth = False

    spells = input("\nSpell learning randomization - ultra, default, none (u/D/n): ")
    if (spells.lower().startswith("u")):
      args.ultra_spells = True
    elif (spells.lower().startswith("n")):
      args.no_spells = False

    zones = input("\nEnemy zone randomization - ultra, default, none (u/D/n): ")
    if (zones.lower().startswith("u")):
      args.ultra_zones = True
    elif (zones.lower().startswith("n")):
      args.no_zones = False

    patterns = input("\nEnemy attack randomization - ultra, default, none (u/D/n): ")
    if (patterns.lower().startswith("u")):
      args.ultra_patterns = True
    elif (patterns.lower().startswith("n")):
      args.no_patterns = False


def randomize(args):

  rom = Rom(args.filename)

  print("\n\nDWRandomizer %s" % VERSION)
  if not args.seed:
    args.seed = random.randint(0, sys.maxsize)
  print("Randomizing %s using random seed %d..." % (args.filename, args.seed))
  random.seed(args.seed)
  flags = ""
  prg = ""

  if args.force:
    print("Verifying checksum...")
    result = rom.verify_checksum()
    if result is False:
      print("Checksum does not match any known ROM.")
      answer = input("Do you want to attempt to randomize anyway? ")
      if not answer.lower().startswith("y"):
        sys.exit(-1)
    else:
      print("Processing Dragon Warrior PRG%d ROM..." % result)
      prg = "PRG%d." % result
      
  else:
    print("Skipping checksum...")

  if args.no_map:
    print("Generating new overworld map...")
    flags += "A"
    while not rom.generate_map():
      print("Error: " + str(rom.owmap.error) + ", retrying...")

  if args.speed_hacks:
    print("Applying game speed hacks...")
    rom.speed_hacks()
    flags += "H"

  if args.no_searchitems:
    print("Shuffling searchable item locations...")
    flags += "I"
    rom.shuffle_searchables()

  if args.no_chests:
    print("Shuffling chest contents...")
    flags += "C"
    rom.shuffle_chests()

  if args.no_towns:
    print("Shuffling town locations...")
    flags += "T"
    rom.shuffle_towns()

  if args.no_zones:
    if args.ultra or args.ultra_zones:
      print("Ultra randomizing enemy zones...")
      flags += "Z"
      rom.randomize_zones(True)
    else:
      print("Randomizing enemy zones...")
      flags += "z"
      rom.randomize_zones()

  if args.no_patterns:
    if args.ultra or args.ultra_patterns:
      print("Ultra randomizing enemy attack patterns...")
      flags += "P"
      rom.randomize_attack_patterns(True)
    else:
      print("Randomizing enemy attack patterns...")
      flags += "p"
      rom.randomize_attack_patterns()

  if args.no_shops:
    print("Randomizing weapon shops...")
    flags += "W"
    rom.randomize_shops()

  if args.no_growth:
    if args.ultra or args.ultra_growth:
      print("Ultra randomizing player stat growth...")
      flags += "G"
      rom.randomize_growth(True)
    else:
      print("Randomizing player stat growth...")
      flags += "g"
      rom.randomize_growth()

  print("Increasing XP/Gold drops to remake levels...")
  rom.update_drops()
  print("Setting enemy HP to remake levels...")
  rom.update_enemy_hp()
  print("Lowering MP requirements to remake levels...")
  rom.update_mp_reqs()

  if args.very_fast_leveling:
    print("Setting XP requirements for levels to 50% of normal...")
    flags += "F"
    rom.lower_xp_reqs(True)
  elif args.fast_leveling:
    print("Setting XP requirements for levels to 75% of normal...")
    flags += "f"
    rom.lower_xp_reqs()

  print("Moving REPEL to level 8...")
  rom.move_repel()

  if args.no_spells:
    if args.ultra or args.ultra_spells:
      print("Ultra randomizing level spells are learned...")
      flags += "M"
      rom.randomize_spell_learning(True)
    else:
      print("Randomizing level spells are learned...")
      flags += "m"
      rom.randomize_spell_learning()

  print("Updating title screen...")
  rom.update_title_screen(args.seed, flags)
  print("Buffing HEAL slightly...")
  print("Patching Northern Shrine...")
  print("Fixing functionality of the fighter's ring (+2 atk)...")
  print("Adding a new throne room exit...")
  print("Bumping encounter rate for zone 0...")
  rom.commit()
  output_filename = "DWRando.%s.%d.%snes" % (flags, args.seed, prg)
  print("Writing output file %s..." % output_filename)
  rom.write(output_filename)
  if args.ips:
    output_filename = "DWRando.%s.%d.%sips" % (flags, args.seed, prg)
    print("Writing output file %s..." % output_filename)
    rom.write(output_filename, rom.patch.encode())
  print ("New ROM Checksum: %s" % rom.sha1())
  print ("IPS Checksum: %s" % rom.sha1(rom.patch.encode()))

if __name__ == "__main__":
  main()

