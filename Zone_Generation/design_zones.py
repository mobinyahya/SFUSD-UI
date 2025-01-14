import sys
import yaml
import csv
import types
sys.path.append("Zone_Generation/")
from Config.Constants import *
import pandas as pd

from Zone_Helper.util import *
# from Zone_Helper.zone_vizualization import ZoneVisualizer
# from integer_program import Integer_Program
from schools import Schools
from students import Students


class DesignZones:
    def __init__(
            self,
            config,
    ):
        self.config = config
        # self.Z: number of zones requested (The number of zones that we need to divide the city into)
        self.Z = int(config["centroids_type"].split("-")[0])  # number of possible zones
        # The building blocks of zones. As a defualt, this is attendance_area
        self.level = config["level"]  # 'Block', 'BlockGroup' or 'attendance_area'

        self.centroid_type = config["centroids_type"]
        self.include_k8 = config["include_k8"]
        self.population_type = config["population_type"]

        self.load_students_and_schools()
        self.construct_datastructures()

        self.load_neighborhood_dict()
        self.initialize_centroids()
        self.initialize_centroid_neighbors()


    def construct_datastructures(self):
        self.N = sum(self.units_data["ge_students"])
        self.F = sum(self.units_data["FRL"]) / (self.N)
        self.U = len(self.units_data.index)
        self.zones = None

        self.seats = (self.units_data["ge_capacity"].astype("int64").to_numpy())
        self.schools = self.units_data['num_schools']
        self.studentsInArea = self.units_data["ge_students"]


        self.units_data[self.level] = self.units_data[self.level].astype("int64")


        self.area2idx = dict(zip(self.units_data[self.level], self.units_data.index))
        self.idx2area = dict(zip(self.units_data.index, self.units_data[self.level]))
        self.sch2area = dict(zip(self.school_df["school_id"], self.school_df[self.level]))

        self.euc_distances = load_euc_distance_data(self.level, self.area2idx)

        print("Level: ", self.level)
        print("Average FRL ratio:       ", self.F)
        print("Number of Areas:       ", self.U)
        print("Number of GE students:       ", self.N)
        print("Number of total students: ", sum(self.units_data["all_prog_students"]))
        print("Number of total seats:    ", sum(self.units_data["all_prog_capacity"]))
        print("Number of GE seats:       ", sum(self.seats))
        print("Number of zones:       ", self.Z)

        # self.save_partial_distances()
        # self.drive_distances = self.load_driving_distance_data()



    def load_students_and_schools(self):
        students_data = Students(self.config)
        schools_data = Schools(self.config)
        self.student_df = students_data.load_student_data()
        self.school_df = schools_data.load_school_data()

        student_stats = self._aggregate_student_data_to_area(self.student_df)
        school_stats = self._aggregate_school_data_to_area(self.school_df)


        self.units_data = student_stats.merge(school_stats, how='outer', on=self.level)
        self.units_data.fillna(0, inplace=True)

        self._load_auxilariy_areas()

        self.units_data.fillna(value=0, inplace=True)
        # if self.level == "BlockGroup":
        #     self.bg2att = load_bg2att(self.level)



    # groupby the student data by area level
    def _aggregate_student_data_to_area(self, student_df):
        # sum_columns = list(student_df.columns)
        # sum_columns.remove("FRL")
        # mean_columns = [self.level, "FRL"]
        #
        # sum_students = student_df[sum_columns].groupby(self.level, as_index=False).sum()
        # mean_students = student_df[mean_columns].groupby(self.level, as_index=False).mean()
        #
        # student_stats = mean_students.merge(sum_students, how="left", on=self.level)
        student_stats = student_df.groupby(self.level, as_index=False).sum()
        student_stats = student_stats[AREA_COLS + [self.level] ]

        for col in student_stats.columns:
            if col not in BUILDING_BLOCKS:
                student_stats[col] /= len(self.config["years"])
        return student_stats

    def _aggregate_school_data_to_area(self, school_df):

        sum_columns = [self.level, "all_prog_capacity", "ge_capacity", "num_schools", "english_score",
                       "math_score", "greatschools_rating", "AvgColorIndex"]
        mean_columns = [self.level, "MetStandards",]

        sum_schools = school_df[sum_columns].groupby(self.level, as_index=False).sum()
        mean_schools = school_df[mean_columns].groupby(self.level, as_index=False).mean()

        return mean_schools.merge(sum_schools, how="left", on=self.level)


    def _load_auxilariy_areas(self):
        # we add areas (blockgroups/blocks) that were missed from guardrail, since there was no student or school in them.
        if (self.level=='BlockGroup') | (self.level=='Block'):
            valid_areas = set(pd.read_csv('Zone_Generation/Zone_Data/block_blockgroup_tract.csv')[self.level])
            census_areas = load_census_shapefile(self.level)[self.level]
            census_areas = set(census_areas)
            census_areas = census_areas - set(AUX_BG)

            common_areas = census_areas.intersection(valid_areas)

            current_areas = set(self.units_data[self.level])

            auxiliary_areas = common_areas - current_areas

            auxiliary_areas_df = pd.DataFrame({self.level: list(auxiliary_areas)})
            self.units_data = self.units_data.append(auxiliary_areas_df, ignore_index=True)
            self.units_data.fillna(value=0, inplace=True)







    def initialize_centroids(self):
        """set the centroids - each one is a block or attendance area depends on the method
        probably best to make it a school"""

        with open("Zone_Generation/Config/automatic_centroids.yaml", "r") as f:
            centroid_configs = yaml.safe_load(f)
        if self.centroid_type not in centroid_configs:
            raise ValueError(
                "The centroids type specified is not defined in centroids.yaml.")

        self.centroid_sch = centroid_configs[self.centroid_type]
        print("Number of centroid schools ", len(self.centroid_sch))

        self.school_df['is_centroid'] = self.school_df['school_id'].apply(lambda x: 1 if x in self.centroid_sch else 0)

        if self.include_k8:
            self.centroid_location = self.school_df[self.school_df['is_centroid'] == 1][['lon', 'lat', 'school_id']]
        else:
            self.centroid_location = self.school_df[(self.school_df['is_centroid'] == 1) & (self.school_df['K-8'] != 1)][['lon', 'lat', 'school_id']]
            self.schools_locations = self.school_df[['lon', 'lat', 'school_id']]


        centroid_areas = [self.sch2area[x] for x in self.centroid_sch]
        self.centroids = [self.area2idx[j] for j in centroid_areas]


    def load_neighborhood_dict(self):
        """ build a dictionary mapping a block group/attendance area to a list
        of its neighboring block groups/attendnace areas"""
        if self.level == "Block":
            file = os.path.expanduser("Zone_Generation/Zone_Data/adjacency_matrix_b.csv")

        elif self.level == "BlockGroup":
            file = os.path.expanduser("Zone_Generation/Zone_Data/adjacency_matrix_bg.csv")

        elif self.level == "attendance_area":
            file = os.path.expanduser("Zone_Generation/Zone_Data/adjacency_matrix_aa.csv")

        with open(file, "r") as f:
            reader = csv.reader(f)
            neighborhoods = list(reader)

        # create dictionary mapping attendance area school id to list of neighbor
        # attendance area ids (similarly, block group number)
        self.neighbors = {}
        for row in neighborhoods:
            # Potential Issue: row[0] is an area number from the neighborhood adjacency matrix,
            # and it should be included as a key in area2idx map.
            if int(row[0]) not in self.area2idx:
                continue
            u = self.area2idx[int(row[0])]
            ngbrs = [
                self.area2idx[int(n)]
                for n in row
                if n != ''
                   and int(n) in list(self.area2idx.keys())
            ]
            ngbrs.remove(u)
            self.neighbors[u] = [n for n in ngbrs]
            for n in ngbrs:
                if n in self.neighbors:
                    if u not in self.neighbors[n]:
                        self.neighbors[n].append(u)
                else:
                    self.neighbors[n] = [u]

    def initialize_centroid_neighbors(self):
        """ for each centroid c and each area v, define a set n(v,c) to be all neighbors of j that are closer to c than j"""
        save_path = os.path.expanduser("Zone_Data/59zone_contiguity_constraint.pkl")

        if (self.level == "Block") and (self.centroid_type == '59-zone-1'):
            if os.path.exists(os.path.expanduser(save_path)):
                with open(save_path, 'rb') as file:
                    self.closer_euc_neighbors = pickle.load(file)
                return


        self.closer_euc_neighbors = {}
        for z in self.centroids:
            for u in range(self.U):
                n = self.neighbors[u]
                closer = [x for x in n
                    if self.euc_distances[z][u]
                       >= self.euc_distances[z][x]
                ]
                self.closer_euc_neighbors[u, z] = closer

        if (self.level == "Block") and (self.centroid_type == '59-zone-1'):
            with open(save_path, 'wb') as file:
                pickle.dump(self.closer_euc_neighbors, file)


    # ---------------------------------------------------------------------------
    # ---------------------------------------------------------------------------

    def save(self, path,  name = "", solve_success = 1):
        filename = os.path.expanduser(path)
        filename += name
        filename += ".csv"

        # save zones themselves
        with open(filename, "w") as outFile:
            writer = csv.writer(outFile, lineterminator="\n")
            if solve_success == 1:
                for z in self.zone_lists:
                    writer.writerow(z)
            else:
                writer.writerow({})


    def solve(self, IP):
        IP.m.update()  # Update the model
        print(f"Total number of dz.m variables: {IP.m.numVars}")
        print(f"Total number of dz.m constraints: {IP.m.numConstrs}")
        exit()
        self.filename = ""
        self.zone_dict = {}

        try:
            IP.m.optimize()
            zone_lists = []
            for z in range(0, self.Z):
                zone = []
                for u in range(0, self.U):
                    if u not in IP.valid_units_per_zone[z]:
                        continue
                    if IP.x[u, z].X >= 0.999:
                        self.zone_dict[self.idx2area[u]] = z
                        zone.append(self.units_data[self.level][u])
                        # add City wide school SF Montessori, even if we are not including city wide schools
                        # 823 is the aa level of SF Montessori school (which has school id 814)
                        if self.idx2area[u] in [823, 60750132001]:
                            self.zone_dict[self.idx2area[u]] = z
                            if self.level == "attendance_area":
                                zone.append(SF_Montessori)
                if not zone == False:
                    zone_lists.append(zone)
            zone_dict = {}
            for idx, schools in enumerate(zone_lists):
                zone_dict = {
                    **zone_dict,
                    **{int(float(s)): idx for s in schools if s != ""},
                }
            # add K-8 schools to dict if using them
            if (self.level == 'attendance_area') & (self.include_k8):
                cw = self.school_df.loc[self.school_df["K-8"] == 1]
                for i, row in cw.iterrows():
                    k8_schno = row["school_id"]
                    z = zone_dict[self.sch2area[int(float(k8_schno))]]
                    zone_dict = {**zone_dict, **{int(float(k8_schno)): z}}
                    zone_lists[z].append(k8_schno)
            self.zone_dict = zone_dict
            self.zone_lists = zone_lists

            return 1

        except gp.GurobiError as e:
            print("gurobi error #" + str(e.errno) + ": " + str(e))
            return -1
        except AttributeError:
            print("attribute error")
            return -1




if __name__ == "__main__":
    with open("Config/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    name = Compute_Name(config)

    dz = DesignZones(config=config)
    IP = Integer_Program(dz)
    IP._initializs_feasiblity_constraints(max_distance=config["max_distance"])

    IP._set_objective_model()
    IP._shortage_constraints(shortage=config["shortage"], overage= config["overage"],
                      all_cap_shortage=config["all_cap_shortage"])

    IP._add_contiguity_constraint()
    IP._add_diversity_constraints(racial_dev=config["racial_dev"], frl_dev=config["frl_dev"])
    IP._add_school_count_constraint()

    solve_success = dz.solve(IP)

    if solve_success == 1:
        print("Resulting zone dictionary: ", dz.zone_dict)
        # dz.save(path=config["path"], name = name + "_AA")

        zv = ZoneVisualizer(config["level"])
        zv.zones_from_dict(dz.zone_dict, centroid_location=dz.centroid_location, save_path=config["path"]+name+"_"+SUFFIX[config["level"]])
        # stats_evaluation(dz, dz.zd)



# Note: when you update the distance/neighboring files, also update the closer_eucledian distance file
# Note: Total number of students in aa level is not the same as blockgroup level.
# Reason: some students, do not have their bg info available
# (but they do have their aa info, and also they pass every other filter, i.e. enrollment)

