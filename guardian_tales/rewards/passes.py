# SPDX-License-Identifier: Apache-2.0
"""Initial free pass rewards from the pinned 3.57.0 public catalogs.

The observed scene selects season 58. Zero experience is level 1 in the
native client; its free reward is 30 reserve stamina. Seasons do not roll over
automatically in this local implementation.
Festival Pass season 41 uses reward set 1; its free level-1 reward is four
festival points. The client displays those with coin item 21484, while the
server stores them in UserFestivalPass.Point rather than inventory.
"""

FIRST_PASS_SEASON = 58
FIRST_PASS_LEVEL = 1
FIRST_PASS_STAMINA = 30
FIRST_FESTIVAL_SEASON = 41
FIRST_FESTIVAL_LEVEL = 1
FIRST_FESTIVAL_POINTS = 4
