

-- manual fixes for addresses with no LGA (these are mostly valid nulls. e.g. ACT has no councils)
-- 149 addresses (as at 202202 will not be fixed -- these are all offshore points, a number being oyster leases and boat moorings

-- all of ACT -- 232,665 rows
update gnaf_202202.address_principal_admin_boundaries
set lga_pid = 'lgaact9999991',
    lga_name = 'Unincorporated ACT'
where state = 'ACT'
;

-- Specific localities
update gnaf_202202.address_principal_admin_boundaries
set lga_pid = 'lgaot9999991',
    lga_name = 'Unincorporated OT (Norfolk Island)'
where locality_pid = 'locc15e0d2d6f2a'
  and lga_pid is null;

update gnaf_202202.address_principal_admin_boundaries
set lga_pid = 'lgaot9999992',
    lga_name = 'Unincorporated OT (Jervis Bay)'
where locality_pid = 'loced195c315de9'
  and lga_pid is null;

update gnaf_202202.address_principal_admin_boundaries
set lga_pid = 'lgasa9999991',
    lga_name = 'Unincorporated SA (Thistle Island)'
where locality_pid = '250190776'
  and lga_pid is null;

-- 35 boatsheds in Hobart
update gnaf_202202.address_principal_admin_boundaries
set lga_pid = 'lgacbffb11990f2',
    lga_name = 'Hobart City'
where locality_pid = 'loc0f7a581b85b7'
  and lga_pid is null;

-- slightly offshore points in SA
update gnaf_202202.address_principal_admin_boundaries
set lga_pid = 'lgaa8d127fa14e7',
    lga_name = 'Ceduna'
where locality_pid = 'loccf8be9dcdacd'
  and lga_pid is null;

-- NSW/QLD border silliness
update gnaf_202202.address_principal_admin_boundaries
set lga_pid = 'lga7872e04f6637',
    lga_name = 'Tenterfield'
where locality_pid = 'loc552bd3aef1b8'
  and lga_pid is null;


select * from gnaf_202202.address_principal_admin_boundaries;
